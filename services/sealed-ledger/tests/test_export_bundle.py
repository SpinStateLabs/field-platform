"""C1: auditor export bundle + ``ledger verify-export``.

Done-when (tasks/todo.md C1): editing one exported event fails verify-export
naming its index; deleting a line fails; a filtered (agent_id) export of an
interleaved two-agent chain verifies via the spine and reports "spine
unverified" when unsigned; tampering summary.json on a signed bundle fails;
wrong key fails; the CLI via CliRunner. The remaining tests pin each guard in
``sealed_ledger.bundle.verify_bundle`` so deleting that guard fails a test.
"""

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from field_core.ledger import GENESIS_HASH, LedgerEvent, compute_event_hash
from field_core.signing import generate_keypair, key_fingerprint, sign_manifest
from sealed_ledger import bundle as bundle_mod
from sealed_ledger.api import create_app
from sealed_ledger.bundle import verify_bundle
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import LedgerStore

runner = CliRunner()


# ------------------------------------------------------------------ helpers


@pytest.fixture()
def store(tmp_path):
    return LedgerStore(tmp_path / "events.jsonl")


@pytest.fixture()
def keys(tmp_path):
    private_pem, public_pem = generate_keypair()
    priv = tmp_path / "sign-private.pem"
    pub = tmp_path / "sign-public.pem"
    priv.write_text(private_pem, encoding="ascii")
    pub.write_text(public_pem, encoding="ascii")
    return {"private": private_pem, "public": public_pem, "priv_path": priv, "pub_path": pub}


def _interleaved(store, pairs=3):
    """a, b, a, b, ... — agent 'a' at even indices, 'b' at odd."""
    for i in range(pairs * 2):
        agent = "a" if i % 2 == 0 else "b"
        store.append("action" if i % 3 else "token.mint", {"seq": i}, agent_id=agent)


def _read(bundle: Path, name: str):
    return json.loads((bundle / name).read_text(encoding="utf-8"))


def _write(bundle: Path, name: str, obj) -> None:
    (bundle / name).write_text(json.dumps(obj, indent=2), encoding="utf-8")


def _lines(bundle: Path) -> list[str]:
    return (bundle / "events.jsonl").read_text(encoding="utf-8").splitlines()


def _set_lines(bundle: Path, lines: list[str]) -> None:
    (bundle / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _verify_cli(bundle: Path, pubkey: Path | None = None):
    args = ["verify-export", str(bundle)]
    if pubkey is not None:
        args += ["--pubkey", str(pubkey)]
    return runner.invoke(cli_app, args)


def _export_cli(store, out_dir: Path, *extra: str):
    result = runner.invoke(
        cli_app, ["export", "--path", str(store.path), "--out-dir", str(out_dir), *extra]
    )
    assert result.exit_code == 0, result.output
    return json.loads(result.stdout)


# ------------------------------------------------------------ bundle layout


def test_bundle_layout_and_pure_event_lines(store, tmp_path):
    _interleaved(store)
    summary = store.export(tmp_path / "exports")
    bundle = Path(summary.bundle_dir)
    assert bundle.parent == tmp_path / "exports"
    assert sorted(p.name for p in bundle.iterdir()) == [
        "chain_proof.json", "events.jsonl", "signature.json", "summary.json",
    ]
    assert Path(summary.path) == bundle / "events.jsonl"

    on_disk = [LedgerEvent(**json.loads(line)) for line in _lines(bundle)]
    assert on_disk == store.events()
    for line in _lines(bundle):
        # F2: `signature` / `signing_failed` are optional and OMITTED from an
        # unsigned line (additive compatibility with deployed pre-F2 images),
        # so a line's keys are a subset of the model fields and a superset of
        # the seven pre-F2 keys.
        keys = set(json.loads(line))
        assert keys <= set(LedgerEvent.model_fields)
        assert keys >= {"event_id", "ts", "event_type", "agent_id", "payload", "prev_hash", "hash"}

    s = _read(bundle, "summary.json")
    assert (s["first_index"], s["last_index"], s["head_index"]) == (0, 5, 5)
    assert s["indices"] == [0, 1, 2, 3, 4, 5]
    assert s["signed"] is False

    proof = _read(bundle, "chain_proof.json")
    assert set(proof) == {"first_index", "last_index", "head_index", "first_prev_hash",
                          "head_hash", "verification", "filters", "spine"}
    assert proof["first_prev_hash"] == GENESIS_HASH
    assert proof["head_hash"] == store.head_hash
    assert proof["verification"] == {"ok": True, "length": 6, "first_break_index": None,
                                     "reason": None}
    assert proof["filters"] == {"since": None, "until": None, "agent_id": None,
                                "event_type": None}
    assert [set(e) for e in proof["spine"]] == [{"index", "event_id", "prev_hash", "hash"}] * 6
    assert [e["index"] for e in proof["spine"]] == list(range(6))

    assert _read(bundle, "signature.json")["signed"] is False


def test_filtered_spine_runs_from_first_exported_index_to_head(store, tmp_path):
    _interleaved(store)
    summary = store.export(tmp_path / "exports", agent_id="b")
    proof = _read(Path(summary.bundle_dir), "chain_proof.json")
    full = store.events()
    assert summary.indices == [1, 3, 5]
    assert (proof["first_index"], proof["last_index"], proof["head_index"]) == (1, 5, 5)
    assert [e["index"] for e in proof["spine"]] == [1, 2, 3, 4, 5]
    assert proof["first_prev_hash"] == full[1].prev_hash == full[0].hash
    assert [e["hash"] for e in proof["spine"]] == [e.hash for e in full[1:]]
    # the full live chain is verified, not just the exported subset
    assert proof["verification"]["length"] == 6
    assert proof["filters"]["agent_id"] == "b"


def test_head_hash_comes_from_the_read_not_the_cached_head(store, tmp_path):
    store.append("action", {"n": 1})
    other_writer = LedgerStore(store.path)
    other_writer.append("action", {"n": 2})  # store's cached head is now stale
    assert store.head_hash != other_writer.head_hash
    summary = store.export(tmp_path / "exports")
    assert summary.head_hash == other_writer.head_hash
    assert summary.head_index == 1
    assert verify_bundle(summary.bundle_dir).ok


def test_exports_never_overwrite_an_existing_bundle(store, tmp_path, monkeypatch):
    from datetime import datetime, timezone

    frozen = datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(bundle_mod, "_utcnow", lambda: frozen)
    store.append("action", {"n": 1})
    first = store.export(tmp_path / "exports")
    store.append("action", {"n": 2})
    second = store.export(tmp_path / "exports")
    assert first.bundle_dir != second.bundle_dir
    assert len(_lines(Path(first.bundle_dir))) == 1
    assert len(_lines(Path(second.bundle_dir))) == 2
    assert verify_bundle(first.bundle_dir).ok and verify_bundle(second.bundle_dir).ok


def test_served_export_writes_signed_false(store, tmp_path, keys):
    _interleaved(store)
    client = TestClient(create_app(store=store))
    r = client.post("/export", params={"out_dir": str(tmp_path / "exports"), "agent_id": "a",
                                       "sign_key": str(keys["priv_path"])})
    assert r.status_code == 200
    summary = r.json()
    assert summary["signed"] is False
    assert summary["event_count"] == 3
    bundle = Path(summary["bundle_dir"])
    assert _read(bundle, "signature.json") == {
        "signed": False, "algorithm": None, "signed_payload": None,
        "key_fingerprint": None, "signature": None,
    }
    assert verify_bundle(bundle, keys["public"]).ok is False  # cannot be passed off as signed


# --------------------------------------------------------- done-when cases


def test_unsigned_bundle_verifies_and_says_spine_unverified(store, tmp_path):
    _interleaved(store)
    summary = _export_cli(store, tmp_path / "exports")
    result = _verify_cli(Path(summary["bundle_dir"]))
    assert result.exit_code == 0, result.output
    assert "spine unverified (unsigned)" in result.output
    assert f"head_hash {store.head_hash}" in result.output


def test_editing_one_exported_event_fails_naming_its_index(store, tmp_path):
    for i in range(5):
        store.append("spend", {"amount": 100 + i}, agent_id="fin-agent")
    bundle = Path(store.export(tmp_path / "exports").bundle_dir)
    lines = _lines(bundle)
    rec = json.loads(lines[2])
    rec["payload"]["amount"] = 1
    lines[2] = json.dumps(rec)
    _set_lines(bundle, lines)

    result = _verify_cli(bundle)
    assert result.exit_code == 1
    assert "index 2" in result.output
    assert "mutated" in result.output
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 2


def test_editing_an_event_in_a_filtered_export_names_its_global_index(store, tmp_path):
    _interleaved(store)
    bundle = Path(store.export(tmp_path / "exports", agent_id="b").bundle_dir)
    lines = _lines(bundle)  # indices 1, 3, 5
    rec = json.loads(lines[1])
    rec["payload"]["seq"] = 999
    lines[1] = json.dumps(rec)
    _set_lines(bundle, lines)
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 3
    result = _verify_cli(bundle)
    assert result.exit_code == 1 and "index 3" in result.output


def test_rehashed_event_fails_against_the_spine(store, tmp_path):
    for i in range(4):
        store.append("spend", {"amount": 100 + i})
    bundle = Path(store.export(tmp_path / "exports").bundle_dir)
    lines = _lines(bundle)
    rec = json.loads(lines[1])
    rec["payload"]["amount"] = 1
    rec["hash"] = compute_event_hash(rec)  # self-consistent forgery of one record
    lines[1] = json.dumps(rec)
    _set_lines(bundle, lines)
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 1
    assert "does not match the spine" in v.reason


def test_deleting_a_line_fails(store, tmp_path):
    for i in range(4):
        store.append("action", {"n": i})
    bundle = Path(store.export(tmp_path / "exports").bundle_dir)
    lines = _lines(bundle)
    del lines[1]
    _set_lines(bundle, lines)
    result = _verify_cli(bundle)
    assert result.exit_code == 1
    assert "index 1" in result.output
    assert "a line was deleted, inserted or reordered" in result.output
    assert verify_bundle(bundle).first_failing_index == 1


def test_deleting_the_last_line_fails(store, tmp_path):
    _interleaved(store)
    bundle = Path(store.export(tmp_path / "exports", agent_id="a").bundle_dir)
    _set_lines(bundle, _lines(bundle)[:-1])  # drop index 4
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 4
    assert "missing" in v.reason


def test_filtered_interleaved_two_agent_export_verifies_via_the_spine(store, tmp_path, keys):
    _interleaved(store, pairs=4)  # a at 0,2,4,6 ; b at 1,3,5,7
    unsigned = _export_cli(store, tmp_path / "unsigned", "--agent-id", "a")
    assert unsigned["indices"] == [0, 2, 4, 6]
    assert unsigned["agents"] == {"a": 4}
    r = _verify_cli(Path(unsigned["bundle_dir"]))
    assert r.exit_code == 0, r.output
    assert "4 event(s) at indices 0..6" in r.output
    assert "spine unverified (unsigned)" in r.output

    signed = _export_cli(store, tmp_path / "signed", "--agent-id", "a",
                         "--sign-key", str(keys["priv_path"]))
    assert signed["signed"] is True
    r = _verify_cli(Path(signed["bundle_dir"]), keys["pub_path"])
    assert r.exit_code == 0, r.output
    assert "spine unverified" not in r.output
    assert "signature valid" in r.output
    assert key_fingerprint(keys["public"]) in r.output
    v = verify_bundle(signed["bundle_dir"], keys["public"])
    assert v.spine_attested and v.head_hash == store.head_hash and v.head_index == 7


def test_signed_bundle_without_pubkey_still_says_spine_unverified(store, tmp_path, keys):
    _interleaved(store)
    signed = _export_cli(store, tmp_path / "s", "--sign-key", str(keys["priv_path"]))
    r = _verify_cli(Path(signed["bundle_dir"]))
    assert r.exit_code == 0
    assert "spine unverified (signed, but no --pubkey given" in r.output
    assert verify_bundle(signed["bundle_dir"]).spine_attested is False


def test_tampering_summary_on_a_signed_bundle_fails(store, tmp_path, keys):
    _interleaved(store)
    signed = _export_cli(store, tmp_path / "s", "--sign-key", str(keys["priv_path"]))
    bundle = Path(signed["bundle_dir"])
    summary = _read(bundle, "summary.json")
    summary["exported_at"] = "2020-01-01T00:00:00+00:00"  # nothing else cross-checks this field
    _write(bundle, "summary.json", summary)
    r = _verify_cli(bundle, keys["pub_path"])
    assert r.exit_code == 1
    assert "signature invalid" in r.output


def test_tampering_chain_proof_on_a_signed_bundle_fails(store, tmp_path, keys):
    _interleaved(store)
    signed = _export_cli(store, tmp_path / "s", "--sign-key", str(keys["priv_path"]))
    bundle = Path(signed["bundle_dir"])
    proof = _read(bundle, "chain_proof.json")
    proof["filters"]["event_type"] = None
    proof["filters"]["since"] = "2000-01-01T00:00:00Z"  # still matches every event
    _write(bundle, "chain_proof.json", proof)
    v = verify_bundle(bundle, keys["public"])
    assert not v.ok and "signature invalid" in v.reason


def test_wrong_key_fails(store, tmp_path, keys):
    _interleaved(store)
    signed = _export_cli(store, tmp_path / "s", "--sign-key", str(keys["priv_path"]))
    _, other_public = generate_keypair()
    other = tmp_path / "other-public.pem"
    other.write_text(other_public, encoding="ascii")
    r = _verify_cli(Path(signed["bundle_dir"]), other)
    assert r.exit_code == 1
    assert "wrong key" in r.output


def test_wrong_key_fails_even_if_the_fingerprint_field_is_doctored(store, tmp_path, keys):
    """The signature is the guard, not the fingerprint comparison."""
    _interleaved(store)
    signed = _export_cli(store, tmp_path / "s", "--sign-key", str(keys["priv_path"]))
    bundle = Path(signed["bundle_dir"])
    _, other_public = generate_keypair()
    sig = _read(bundle, "signature.json")
    sig["key_fingerprint"] = key_fingerprint(other_public)
    _write(bundle, "signature.json", sig)
    v = verify_bundle(bundle, other_public)
    assert not v.ok and "signature invalid" in v.reason


def test_unsigned_bundle_with_pubkey_fails(store, tmp_path, keys):
    _interleaved(store)
    unsigned = _export_cli(store, tmp_path / "u")
    r = _verify_cli(Path(unsigned["bundle_dir"]), keys["pub_path"])
    assert r.exit_code == 1
    assert "unsigned" in r.output

    # A 0-byte --pubkey (what a failed copy of the key leaves behind) is still
    # "a key was supplied": it must not be read as "no --pubkey" and pass.
    empty = tmp_path / "empty-public.pem"
    empty.write_bytes(b"")
    r = _verify_cli(Path(unsigned["bundle_dir"]), empty)
    assert r.exit_code == 1, r.output
    assert "bundle is unsigned but a public key was supplied" in r.output
    assert not verify_bundle(unsigned["bundle_dir"], "").ok


def _relink_forgery(bundle: Path) -> None:
    """Replace the exported event at index 2 and re-link the spine after it.

    Only possible without the key; the exported events at 0 and 4 and every
    count stay untouched.
    """
    lines = _lines(bundle)
    summary = _read(bundle, "summary.json")
    j = summary["indices"].index(2)
    rec = json.loads(lines[j])
    rec["payload"]["seq"] = 777
    rec["hash"] = compute_event_hash(rec)
    lines[j] = json.dumps(rec)
    _set_lines(bundle, lines)
    proof = _read(bundle, "chain_proof.json")
    first = proof["first_index"]
    proof["spine"][2 - first]["hash"] = rec["hash"]
    proof["spine"][3 - first]["prev_hash"] = rec["hash"]
    _write(bundle, "chain_proof.json", proof)


def test_unsigned_filtered_bundle_cannot_detect_a_relinked_forgery(store, tmp_path, keys):
    """The honest limit: a filtered bundle's gaps are hash-only, so without the
    signature an exported event can be replaced and the gap re-linked."""
    _interleaved(store)
    unsigned = Path(_export_cli(store, tmp_path / "u", "--agent-id", "a")["bundle_dir"])
    signed = Path(_export_cli(store, tmp_path / "s", "--agent-id", "a",
                              "--sign-key", str(keys["priv_path"]))["bundle_dir"])
    _relink_forgery(unsigned)
    _relink_forgery(signed)

    forged_unsigned = _verify_cli(unsigned)
    assert forged_unsigned.exit_code == 0, forged_unsigned.output
    assert "spine unverified (unsigned)" in forged_unsigned.output
    assert f"head_hash {store.head_hash}" in forged_unsigned.output  # the head still "matches"
    assert "filtered: spine gaps are hash-only" in forged_unsigned.output

    forged_signed = _verify_cli(signed, keys["pub_path"])
    assert forged_signed.exit_code == 1
    assert "signature invalid" in forged_signed.output


def test_contiguous_bundle_detects_the_same_forgery_without_a_signature(store, tmp_path):
    _interleaved(store)
    bundle = Path(_export_cli(store, tmp_path / "u")["bundle_dir"])
    intact = _verify_cli(bundle)
    assert intact.exit_code == 0 and "contiguous: every link from index 0" in intact.output
    _relink_forgery(bundle)
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 3  # index 3 is exported; its prev_hash is hashed


def test_unsigned_bundle_head_can_be_forged_but_not_under_signature(store, tmp_path, keys):
    _interleaved(store)
    unsigned = Path(_export_cli(store, tmp_path / "u", "--agent-id", "a")["bundle_dir"])
    signed = Path(_export_cli(store, tmp_path / "s", "--agent-id", "a",
                              "--sign-key", str(keys["priv_path"]))["bundle_dir"])
    for bundle in (unsigned, signed):
        proof = _read(bundle, "chain_proof.json")
        summary = _read(bundle, "summary.json")
        proof["spine"][-1]["hash"] = "f" * 64  # index 5 is not exported
        proof["head_hash"] = summary["head_hash"] = "f" * 64
        _write(bundle, "chain_proof.json", proof)
        _write(bundle, "summary.json", summary)
    assert verify_bundle(unsigned).ok  # internal consistency only
    v = verify_bundle(signed, keys["public"])
    assert not v.ok and "signature invalid" in v.reason


# ----------------------------------------------------- guard-by-guard tests


def _unsigned_bundle(store, tmp_path, **filters) -> Path:
    _interleaved(store)
    return Path(store.export(tmp_path / "exports", **filters).bundle_dir)


def test_spine_link_break_names_its_index(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path, agent_id="a")  # indices 0,2,4 ; spine 0..5
    proof = _read(bundle, "chain_proof.json")
    proof["spine"][3]["prev_hash"] = "e" * 64
    _write(bundle, "chain_proof.json", proof)
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 3 and "spine link break" in v.reason

    # a break AT an exported index is still reported as the spine break
    bundle2 = Path(store.export(tmp_path / "e2", agent_id="a").bundle_dir)
    proof = _read(bundle2, "chain_proof.json")
    proof["spine"][2]["prev_hash"] = "e" * 64
    _write(bundle2, "chain_proof.json", proof)
    v2 = verify_bundle(bundle2)
    assert not v2.ok and v2.first_failing_index == 2 and "spine link break" in v2.reason


def test_spine_must_start_at_first_prev_hash(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path, agent_id="b")
    proof = _read(bundle, "chain_proof.json")
    proof["first_prev_hash"] = "d" * 64
    _write(bundle, "chain_proof.json", proof)
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 1


def test_spine_must_end_at_head_hash(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path)
    for name in ("chain_proof.json", "summary.json"):
        doc = _read(bundle, name)
        doc["head_hash"] = "c" * 64
        _write(bundle, name, doc)
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 5 and "head_hash" in v.reason


def test_spine_must_be_contiguous_to_head(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path, agent_id="a")
    proof = _read(bundle, "chain_proof.json")
    del proof["spine"][-1]  # drop index 5
    _write(bundle, "chain_proof.json", proof)
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 5

    bundle2 = Path(store.export(tmp_path / "e2", agent_id="a").bundle_dir)
    proof = _read(bundle2, "chain_proof.json")
    proof["spine"][2]["index"] = 7
    _write(bundle2, "chain_proof.json", proof)
    v2 = verify_bundle(bundle2)
    assert not v2.ok and v2.first_failing_index == 2 and "contiguous" in v2.reason


def test_spine_may_not_run_past_head(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path)
    proof = _read(bundle, "chain_proof.json")
    last = proof["spine"][-1]
    proof["spine"].append({"index": 6, "event_id": "x", "prev_hash": last["hash"],
                           "hash": last["hash"]})
    _write(bundle, "chain_proof.json", proof)
    v = verify_bundle(bundle)
    assert not v.ok and "past head_index" in v.reason


def test_counts_are_recomputed(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path)
    summary = _read(bundle, "summary.json")
    summary["agents"] = {"a": 6}
    _write(bundle, "summary.json", summary)
    v = verify_bundle(bundle)
    assert not v.ok and "agents" in v.reason

    bundle2 = Path(store.export(tmp_path / "e2").bundle_dir)
    summary = _read(bundle2, "summary.json")
    summary["event_types"] = {"action": 6}
    _write(bundle2, "summary.json", summary)
    assert "event_types" in verify_bundle(bundle2).reason


def test_first_and_last_ts_are_checked(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path)
    summary = _read(bundle, "summary.json")
    summary["last_ts"] = "2099-01-01T00:00:00+00:00"
    _write(bundle, "summary.json", summary)
    v = verify_bundle(bundle)
    assert not v.ok and "last_ts" in v.reason


def test_event_count_and_indices_must_agree(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path, agent_id="a")
    summary = _read(bundle, "summary.json")
    summary["event_count"] = 2
    _write(bundle, "summary.json", summary)
    v = verify_bundle(bundle)
    assert not v.ok and "event_count" in v.reason


def test_extra_line_not_listed_in_summary_fails(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path, agent_id="a")
    lines = _lines(bundle)
    _set_lines(bundle, lines + [lines[-1]])
    v = verify_bundle(bundle)
    assert not v.ok
    assert "events.jsonl has 4 events but summary.json lists 3" in v.reason


def test_exported_events_must_match_the_recorded_filters(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path)  # unfiltered: a and b
    proof = _read(bundle, "chain_proof.json")
    proof["filters"]["agent_id"] = "a"
    _write(bundle, "chain_proof.json", proof)
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 1 and "filters" in v.reason


def test_line_with_an_extra_key_is_not_a_pure_event(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path)
    lines = _lines(bundle)
    rec = json.loads(lines[2])
    rec["note"] = "auditor-approved"
    lines[2] = json.dumps(rec)
    _set_lines(bundle, lines)
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 2 and "pure LedgerEvent" in v.reason


def test_reordered_lines_fail(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path)
    lines = _lines(bundle)
    lines[2], lines[3] = lines[3], lines[2]
    _set_lines(bundle, lines)
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 2


def test_bundle_of_an_already_broken_chain_fails_verify_export(store, tmp_path):
    for i in range(4):
        store.append("action", {"n": i})
    lines = store.path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[1])
    rec["payload"]["n"] = 42
    lines[1] = json.dumps(rec)
    store.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary = store.export(tmp_path / "exports", since="2000-01-01T00:00:00Z")
    assert summary.verification.ok is False
    r = _verify_cli(Path(summary.bundle_dir))
    assert r.exit_code == 1
    assert "index 1" in r.output and "already broken" in r.output


def test_signed_flag_must_agree_between_summary_and_signature(store, tmp_path, keys):
    _interleaved(store)
    signed = Path(_export_cli(store, tmp_path / "s", "--sign-key", str(keys["priv_path"]))["bundle_dir"])
    _write(signed, "signature.json", {"signed": False})  # strip the signature
    v = verify_bundle(signed)
    assert not v.ok and "disagree about whether the bundle is signed" in v.reason


def test_signed_bundle_needs_a_signature_and_ed25519(store, tmp_path, keys):
    _interleaved(store)
    signed = Path(_export_cli(store, tmp_path / "s", "--sign-key", str(keys["priv_path"]))["bundle_dir"])
    sig = _read(signed, "signature.json")
    _write(signed, "signature.json", {**sig, "signature": None})
    assert "carries no signature" in verify_bundle(signed, keys["public"]).reason
    _write(signed, "signature.json", {**sig, "algorithm": "none"})
    assert "not supported" in verify_bundle(signed, keys["public"]).reason

    # the other half of the guard: a signature but no key_fingerprint, with
    # and without a key (without the guard: exit 0, or a TypeError traceback)
    _write(signed, "signature.json", {**sig, "key_fingerprint": None})
    for pubkey in (None, keys["pub_path"]):
        r = _verify_cli(signed, pubkey)
        assert r.exit_code == 1, r.output
        assert "says signed but carries no signature or key_fingerprint" in r.output
        assert r.exception is None or isinstance(r.exception, SystemExit)


def test_missing_file_fails(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path)
    (bundle / "chain_proof.json").unlink()
    r = _verify_cli(bundle)
    assert r.exit_code == 1 and "missing chain_proof.json" in r.output


def test_signature_is_over_the_documented_payload(store, tmp_path, keys):
    """An independent verifier can rebuild the signed bytes from the two files."""
    from field_core.signing import verify_manifest

    _interleaved(store)
    bundle = Path(_export_cli(store, tmp_path / "s", "--sign-key", str(keys["priv_path"]))["bundle_dir"])
    sig = _read(bundle, "signature.json")
    payload = {"summary": _read(bundle, "summary.json"),
               "chain_proof": _read(bundle, "chain_proof.json")}
    assert verify_manifest(payload, sig["signature"], keys["public"])
    assert sig["signature"] == sign_manifest(payload, keys["private"])  # Ed25519 is deterministic
    assert sig["key_fingerprint"] == key_fingerprint(keys["public"])
    assert sig["algorithm"] == "ed25519"


def test_bad_sign_key_writes_nothing_and_exits_2(store, tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    store.append("action")
    ec_pem = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    for i, text in enumerate([ec_pem, "not a key", ""]):
        key = tmp_path / f"bad-{i}.pem"
        key.write_text(text, encoding="ascii")
        r = runner.invoke(cli_app, ["export", "--path", str(store.path),
                                    "--out-dir", str(tmp_path / f"out-{i}"),
                                    "--sign-key", str(key)])
        assert r.exit_code == 2, r.output
        assert not (tmp_path / f"out-{i}").exists()


def test_unreadable_key_files_are_usage_errors(store, tmp_path):
    _interleaved(store)
    missing = tmp_path / "no-such-key.pem"
    r = runner.invoke(cli_app, ["export", "--path", str(store.path), "--out-dir",
                                str(tmp_path / "x"), "--sign-key", str(missing)])
    assert r.exit_code == 2 and "cannot read --sign-key" in r.output
    assert not (tmp_path / "x").exists()
    bundle = Path(store.export(tmp_path / "e").bundle_dir)
    r = _verify_cli(bundle, missing)
    assert r.exit_code == 2 and "cannot read --pubkey" in r.output


def test_empty_chain_and_empty_selection_verify(store, tmp_path):
    empty = store.export(tmp_path / "e0")
    assert (empty.event_count, empty.head_index, empty.head_hash) == (0, None, GENESIS_HASH)
    assert verify_bundle(empty.bundle_dir).ok
    _interleaved(store)
    none = store.export(tmp_path / "e1", agent_id="nobody")
    assert none.event_count == 0 and none.first_index is None and none.head_index == 5
    r = _verify_cli(Path(none.bundle_dir))
    assert r.exit_code == 0 and "0 events" in r.output


# ------------------------------------------------ header and file guards


def _both(bundle: Path, mutate) -> None:
    """Apply the same edit to summary.json and chain_proof.json."""
    for name in ("summary.json", "chain_proof.json"):
        doc = _read(bundle, name)
        mutate(doc)
        _write(bundle, name, doc)


@pytest.mark.parametrize("field,value", [
    ("head_hash", "b" * 64), ("head_index", 4), ("first_index", 1), ("last_index", 4),
])
def test_summary_header_must_match_chain_proof(store, tmp_path, field, value):
    bundle = _unsigned_bundle(store, tmp_path)
    summary = _read(bundle, "summary.json")
    summary[field] = value
    _write(bundle, "summary.json", summary)
    v = verify_bundle(bundle)
    assert not v.ok and f"disagree on {field}" in v.reason


def test_summary_verification_must_match_chain_proof(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path)
    summary = _read(bundle, "summary.json")
    summary["verification"]["length"] = 99
    _write(bundle, "summary.json", summary)
    v = verify_bundle(bundle)
    assert not v.ok and "different chain verifications" in v.reason


def test_verification_length_must_cover_the_chain_to_head(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path)
    _both(bundle, lambda d: d["verification"].update(length=3))
    v = verify_bundle(bundle)
    assert not v.ok and "verification covered 3 events" in v.reason


def test_empty_chain_bundle_must_carry_the_zero_head(store, tmp_path):
    bundle = Path(store.export(tmp_path / "e").bundle_dir)
    _both(bundle, lambda d: d.update(head_hash="a" * 64))
    v = verify_bundle(bundle)
    assert not v.ok and "zero head_hash" in v.reason


def test_indices_must_be_strictly_increasing(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path)
    lines = _lines(bundle)
    lines[2], lines[3] = lines[3], lines[2]
    _set_lines(bundle, lines)
    summary = _read(bundle, "summary.json")
    summary["indices"] = [0, 1, 3, 2, 4, 5]  # lines and indices agree; the order is a lie
    _write(bundle, "summary.json", summary)
    v = verify_bundle(bundle)
    assert not v.ok and "strictly increasing" in v.reason and v.first_failing_index == 2


def test_indices_must_end_at_last_index(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path)
    _both(bundle, lambda d: d.update(last_index=4))
    v = verify_bundle(bundle)
    assert not v.ok and "end at last_index" in v.reason


def test_exported_events_on_an_empty_chain_are_refused(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path)

    def empty_head(d):
        d.update(head_index=None, head_hash=GENESIS_HASH)
        d["verification"]["length"] = 0

    _both(bundle, empty_head)
    v = verify_bundle(bundle)
    assert not v.ok and "chain is empty" in v.reason


def test_empty_selection_may_not_claim_a_spine_or_first_prev_hash(store, tmp_path):
    _interleaved(store)
    bundle = Path(store.export(tmp_path / "e", agent_id="nobody").bundle_dir)
    proof = _read(bundle, "chain_proof.json")
    proof["spine"] = [{"index": 5, "event_id": "x", "prev_hash": "0" * 64, "hash": "1" * 64}]
    _write(bundle, "chain_proof.json", proof)
    assert "claims a first/last index or spine" in verify_bundle(bundle).reason

    bundle2 = Path(store.export(tmp_path / "e2", agent_id="nobody").bundle_dir)
    proof = _read(bundle2, "chain_proof.json")
    proof["first_prev_hash"] = "0" * 64
    _write(bundle2, "chain_proof.json", proof)
    assert "claims a first_prev_hash" in verify_bundle(bundle2).reason


def test_unusable_filters_fail_cleanly(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path)
    proof = _read(bundle, "chain_proof.json")
    proof["filters"]["since"] = "garbage"
    _write(bundle, "chain_proof.json", proof)
    v = verify_bundle(bundle)
    assert not v.ok and "filters unusable" in v.reason


def test_index_beyond_the_spine_fails(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path)  # 0..5
    summary = _read(bundle, "summary.json")
    summary["indices"][-1] = 9
    summary["last_index"] = 9
    _write(bundle, "summary.json", summary)
    proof = _read(bundle, "chain_proof.json")
    proof["last_index"] = 9
    _write(bundle, "chain_proof.json", proof)
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 9 and "not covered by the spine" in v.reason


def test_exported_prev_hash_must_match_the_spine(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path, agent_id="b")  # first_index 1
    proof = _read(bundle, "chain_proof.json")
    proof["first_prev_hash"] = "9" * 64
    proof["spine"][0]["prev_hash"] = "9" * 64  # the spine walk is consistent again
    _write(bundle, "chain_proof.json", proof)
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 1 and "re-linked" in v.reason


def test_spine_failure_outranks_an_unindexed_event_failure(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path, agent_id="a")  # 0,2,4 ; head 5
    _both(bundle, lambda d: d.update(head_hash="7" * 64))
    lines = _lines(bundle)
    _set_lines(bundle, lines + [lines[0]])
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 5


def test_non_iso_ts_inside_a_windowed_bundle_fails_cleanly(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path, since="2000-01-01T00:00:00Z")  # 0..5
    lines = _lines(bundle)
    rec = json.loads(lines[-1])
    rec["ts"] = "not-a-time"
    rec["hash"] = compute_event_hash(rec)
    lines[-1] = json.dumps(rec)
    _set_lines(bundle, lines)
    proof = _read(bundle, "chain_proof.json")
    proof["spine"][-1]["hash"] = rec["hash"]
    _write(bundle, "chain_proof.json", proof)
    _both(bundle, lambda d: d.update(head_hash=rec["hash"]))
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 5 and "not ISO 8601" in v.reason


def test_negative_index_is_not_a_valid_bundle(store, tmp_path):
    bundle = _unsigned_bundle(store, tmp_path)
    proof = _read(bundle, "chain_proof.json")
    proof["spine"][0]["index"] = -1
    _write(bundle, "chain_proof.json", proof)
    assert "not a valid bundle file" in verify_bundle(bundle).reason


def test_unreadable_and_malformed_files_fail_cleanly(store, tmp_path):
    assert "not a bundle directory" in verify_bundle(tmp_path / "nope").reason
    bundle = _unsigned_bundle(store, tmp_path)
    (bundle / "summary.json").write_text("{", encoding="utf-8")
    assert "summary.json unreadable" in verify_bundle(bundle).reason

    bundle2 = Path(store.export(tmp_path / "e2").bundle_dir)
    proof = _read(bundle2, "chain_proof.json")
    proof["note"] = "trust me"
    _write(bundle2, "chain_proof.json", proof)
    assert "chain_proof.json is not a valid bundle file" in verify_bundle(bundle2).reason


def test_non_ed25519_pubkey_fails_cleanly(store, tmp_path, keys):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    _interleaved(store)
    signed = Path(_export_cli(store, tmp_path / "s", "--sign-key", str(keys["priv_path"]))["bundle_dir"])
    ec_pub = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode("ascii")
    v = verify_bundle(signed, ec_pub)
    assert not v.ok and "supplied public key is not usable" in v.reason

    # a 0-byte --pubkey file is an unusable key, never "no key given"
    empty = tmp_path / "empty-public.pem"
    empty.write_bytes(b"")
    r = _verify_cli(signed, empty)
    assert r.exit_code == 1, r.output
    assert "supplied public key is not usable" in r.output
    assert "signature not checked" not in r.output


# ----------------------------------- review fixes (windowed, deletion, parsing)


def _timed_chain(store, n: int, agent_id: str = "fin") -> list[LedgerEvent]:
    """n spends one minute apart, written straight to the store's file so every
    ts is distinct (store.append can repeat a ts on a coarse clock)."""
    from field_core.ledger import make_event

    events, prev = [], GENESIS_HASH
    for i in range(n):
        ev = make_event("spend", {"seq": i, "amount": 100 + i}, prev_hash=prev,
                        agent_id=agent_id, ts=f"2026-09-12T10:{i:02d}:00+00:00")
        events.append(ev)
        prev = ev.hash
    store.path.write_text("".join(e.model_dump_json() + "\n" for e in events), encoding="utf-8")
    return events


def _recount(bundle: Path) -> None:
    """Re-edit summary.json so its counts and first/last ts match events.jsonl."""
    summary = _read(bundle, "summary.json")
    recs = [json.loads(line) for line in _lines(bundle) if line.strip()]
    types: dict[str, int] = {}
    agents: dict[str, int] = {}
    for rec in recs:
        types[rec["event_type"]] = types.get(rec["event_type"], 0) + 1
        key = rec["agent_id"] or "<none>"
        agents[key] = agents.get(key, 0) + 1
    summary.update(event_types=types, agents=agents, event_count=len(recs),
                   first_ts=recs[0]["ts"] if recs else None,
                   last_ts=recs[-1]["ts"] if recs else None)
    _write(bundle, "summary.json", summary)


def test_a_windowed_export_that_ends_before_head_is_not_contiguous(store, tmp_path):
    """--until before head: indices 0..3 are contiguous among themselves, but
    4 and 5 are hash-only spine entries. Forging every exported event and
    re-linking index 4 keeps the head equal to an off-box anchor, so the
    verifier must NOT claim that an anchor match covers the exported events."""
    events = _timed_chain(store, 6)
    anchor = store.events()[-1].hash  # an off-box anchor at chain_length 6
    summary = _export_cli(store, tmp_path / "w", "--until", events[3].ts)
    bundle = Path(summary["bundle_dir"])
    assert (summary["indices"], summary["head_index"]) == ([0, 1, 2, 3], 5)

    intact = verify_bundle(bundle)
    assert intact.ok and intact.contiguous is False
    r = _verify_cli(bundle)
    assert r.exit_code == 0, r.output
    assert "filtered: spine gaps are hash-only" in r.output
    assert "contiguous:" not in r.output

    lines = _lines(bundle)
    proof = _read(bundle, "chain_proof.json")
    prev = proof["first_prev_hash"]
    forged = []
    for j, line in enumerate(lines):
        rec = json.loads(line)
        rec["payload"]["amount"] = 1
        rec["prev_hash"] = prev
        rec["hash"] = compute_event_hash(rec)
        proof["spine"][j].update(prev_hash=prev, hash=rec["hash"])
        prev = rec["hash"]
        forged.append(json.dumps(rec))
    proof["spine"][len(lines)]["prev_hash"] = prev  # index 4: hash-only, re-linked
    _set_lines(bundle, forged)
    _write(bundle, "chain_proof.json", proof)

    r = _verify_cli(bundle)
    assert r.exit_code == 0, r.output  # the documented limit of an unsigned filtered bundle
    assert f"head_hash {anchor}" in r.output  # the head still "matches" the anchor
    assert "filtered: spine gaps are hash-only" in r.output
    assert "contiguous:" not in r.output
    assert verify_bundle(bundle).contiguous is False


def _unfiltered_bundle(store, tmp_path) -> Path:
    _interleaved(store, pairs=4)  # 8 events, head 7
    bundle = Path(_export_cli(store, tmp_path / "u")["bundle_dir"])
    assert _read(bundle, "chain_proof.json")["filters"] == {
        "since": None, "until": None, "agent_id": None, "event_type": None}
    return bundle


def test_deleting_a_middle_event_from_an_unfiltered_bundle_fails_even_with_summary_reedited(store, tmp_path):
    bundle = _unfiltered_bundle(store, tmp_path)
    lines = _lines(bundle)
    del lines[2]
    _set_lines(bundle, lines)
    summary = _read(bundle, "summary.json")
    summary["indices"] = [0, 1, 3, 4, 5, 6, 7]
    _write(bundle, "summary.json", summary)
    _recount(bundle)

    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 2
    assert "missing from an unfiltered export" in v.reason
    r = _verify_cli(bundle)
    assert r.exit_code == 1 and "index 2" in r.output, r.output


@pytest.mark.parametrize("dropped", [1, 2], ids=["last-event", "last-two"])
def test_dropping_the_tail_of_an_unfiltered_bundle_fails(store, tmp_path, dropped):
    """dropped=1 pins the boundary: a `< expected_length - 1` off-by-one would
    let a single-event tail deletion verify as 'every index is exported'."""
    bundle = _unfiltered_bundle(store, tmp_path)
    _set_lines(bundle, _lines(bundle)[:-dropped])
    summary, proof = _read(bundle, "summary.json"), _read(bundle, "chain_proof.json")
    summary["indices"] = summary["indices"][:-dropped]
    summary["last_index"] = proof["last_index"] = 7 - dropped
    _write(bundle, "summary.json", summary)
    _write(bundle, "chain_proof.json", proof)
    _recount(bundle)

    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 8 - dropped
    assert "missing from an unfiltered export" in v.reason
    r = _verify_cli(bundle)
    assert r.exit_code == 1, r.output
    assert "every index 0..7 is exported" not in r.output


def test_dropping_the_first_events_of_an_unfiltered_bundle_fails(store, tmp_path):
    bundle = _unfiltered_bundle(store, tmp_path)
    _set_lines(bundle, _lines(bundle)[3:])
    summary, proof = _read(bundle, "summary.json"), _read(bundle, "chain_proof.json")
    summary["indices"] = summary["indices"][3:]
    summary["first_index"] = proof["first_index"] = 3
    proof["first_prev_hash"] = proof["spine"][3]["prev_hash"]
    proof["spine"] = proof["spine"][3:]
    _write(bundle, "summary.json", summary)
    _write(bundle, "chain_proof.json", proof)
    _recount(bundle)

    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 0
    assert "missing from an unfiltered export" in v.reason
    r = _verify_cli(bundle)
    assert r.exit_code == 1, r.output
    assert "contiguous:" not in r.output


def test_emptying_an_unfiltered_bundle_fails(store, tmp_path):
    bundle = _unfiltered_bundle(store, tmp_path)
    (bundle / "events.jsonl").write_text("", encoding="utf-8")
    summary, proof = _read(bundle, "summary.json"), _read(bundle, "chain_proof.json")
    summary.update(indices=[], first_index=None, last_index=None)
    proof.update(first_index=None, last_index=None, first_prev_hash=None, spine=[])
    _write(bundle, "summary.json", summary)
    _write(bundle, "chain_proof.json", proof)
    _recount(bundle)
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 0
    assert "missing from an unfiltered export" in v.reason


def test_an_intact_unfiltered_bundle_says_every_index_is_exported(store, tmp_path):
    bundle = _unfiltered_bundle(store, tmp_path)
    v = verify_bundle(bundle)
    assert v.ok and v.unfiltered and v.contiguous
    r = _verify_cli(bundle)
    assert r.exit_code == 0, r.output
    assert "filters: none — every index 0..7 is exported (verified)" in r.output
    assert "contiguous: every link from index 0 to head" in r.output

    filtered = Path(_export_cli(store, tmp_path / "f", "--agent-id", "a")["bundle_dir"])
    assert verify_bundle(filtered).unfiltered is False
    r = _verify_cli(filtered)
    assert "filters: agent_id='a' — completeness of a filtered export is not provable" in r.output


@pytest.mark.parametrize("filtered", [False, True], ids=["unfiltered", "agent-filtered"])
def test_first_index_zero_must_start_at_the_genesis_hash(store, tmp_path, filtered):
    """A rewrite from index 0 that links event 0 to a non-genesis prev_hash is
    otherwise self-consistent; the chain's start is not negotiable, whether or
    not the export recorded a filter."""
    if filtered:
        _interleaved(store, pairs=4)
        bundle = Path(_export_cli(store, tmp_path / "g", "--agent-id", "a")["bundle_dir"])
    else:
        bundle = _unfiltered_bundle(store, tmp_path)
    proof, summary = _read(bundle, "chain_proof.json"), _read(bundle, "summary.json")
    recs = dict(zip(summary["indices"], (json.loads(line) for line in _lines(bundle))))
    assert 0 in recs and (len(recs) < len(proof["spine"])) == filtered
    prev = "a" * 64
    proof["first_prev_hash"] = prev
    for entry in proof["spine"]:
        rec = recs.get(entry["index"])
        if rec is not None:
            rec["prev_hash"] = prev
            rec["hash"] = compute_event_hash(rec)
            entry.update(prev_hash=prev, hash=rec["hash"])
        else:  # an index the filter left out: only its spine link exists
            entry.update(prev_hash=prev, hash=hashlib.sha256(prev.encode()).hexdigest())
        prev = entry["hash"]
    proof["head_hash"] = summary["head_hash"] = prev
    _set_lines(bundle, [json.dumps(recs[i]) for i in sorted(recs)])
    _write(bundle, "chain_proof.json", proof)
    _write(bundle, "summary.json", summary)

    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 0
    assert "not the genesis hash" in v.reason


@pytest.mark.parametrize("separator", ["\u2028", "\u2029", "\x85"], ids=["U+2028", "U+2029", "NEL"])
def test_a_genuine_payload_with_a_unicode_line_separator_verifies(store, tmp_path, separator):
    """pydantic writes these raw inside JSON strings (JSON allows it). The
    ledger reads them fine, so the export must too: a false tamper verdict on
    a genuine bundle is as wrong as a false pass."""
    store.append("action", {"n": 1}, agent_id="a")
    event = store.append("action", {"note": f"invoice note{separator}second line"}, agent_id="a")
    store.append("action", {"n": 3}, agent_id="a")
    assert separator in event.model_dump_json()
    assert store.verify().ok

    bundle = Path(_export_cli(store, tmp_path / "e")["bundle_dir"])
    assert separator in (bundle / "events.jsonl").read_text(encoding="utf-8")
    r = _verify_cli(bundle)
    assert r.exit_code == 0, r.output
    assert "3 event(s) at indices 0..2" in r.output


def test_a_duplicate_key_decoy_in_an_event_line_fails_even_signed(store, tmp_path, keys):
    """json.loads keeps the LAST duplicate, a human or grep sees the FIRST: the
    decoy must be refused, not verified under the genuine signature."""
    _interleaved(store)
    signed = Path(_export_cli(store, tmp_path / "s", "--sign-key", str(keys["priv_path"]))["bundle_dir"])
    lines = _lines(signed)
    assert lines[2].startswith('{"event_id"')
    lines[2] = lines[2].replace('{"event_id"', '{"payload":{"seq":2,"amount":1},"event_id"', 1)
    _set_lines(signed, lines)
    v = verify_bundle(signed, keys["public"])
    assert not v.ok and v.first_failing_index == 2
    assert "duplicate key 'payload'" in v.reason
    r = _verify_cli(signed, keys["pub_path"])
    assert r.exit_code == 1 and "index 2" in r.output, r.output

    # nested: a duplicate inside the payload object
    bundle = Path(store.export(tmp_path / "n").bundle_dir)
    lines = _lines(bundle)
    assert '"payload":{' in lines[1]
    lines[1] = lines[1].replace('"payload":{', '"payload":{"seq":999,', 1)
    _set_lines(bundle, lines)
    v = verify_bundle(bundle)
    assert not v.ok and v.first_failing_index == 1 and "duplicate key 'seq'" in v.reason


@pytest.mark.parametrize("name", ["summary.json", "chain_proof.json", "signature.json"])
def test_a_duplicate_key_decoy_in_a_bundle_file_fails_even_signed(store, tmp_path, keys, name):
    _interleaved(store)
    signed = Path(_export_cli(store, tmp_path / "s", "--sign-key", str(keys["priv_path"]))["bundle_dir"])
    text = (signed / name).read_text(encoding="utf-8")
    assert text.startswith("{\n")
    key = {"summary.json": "head_hash", "chain_proof.json": "head_hash", "signature.json": "signed"}[name]
    decoy = '"' + "f" * 64 + '"' if key == "head_hash" else "false"
    (signed / name).write_text('{\n  "' + key + '": ' + decoy + "," + text[1:], encoding="utf-8")
    assert json.loads((signed / name).read_text(encoding="utf-8"))  # plain json.loads accepts it
    v = verify_bundle(signed, keys["public"])
    assert not v.ok
    assert f"{name} unreadable: duplicate key '{key}'" in v.reason
    assert _verify_cli(signed, keys["pub_path"]).exit_code == 1
