"""F2 — per-event ledger signatures + fail-closed appends (sealed-ledger).

Done-when (tasks/todo.md Phase F, F2): appended events verify; a tampered
and re-linked signed event fails ``verify --event-pubkey`` naming the index;
key unset => unsigned events, ``signing: off``, no ``signature`` key in the
JSON line; require-signing with no key => start-type 503, stop-type 201 with
``signing_failed: true``; wrong pubkey => exit 1; a pre-F2 fixture verifies
with the unsigned count printed; served ``/verify`` unchanged;
``verify-export`` on a bundle carrying signed events passes; rotation with
signed events verifies. Every refusal branch has the test that fails when the
branch is deleted (named in the README rows).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from field_core.ledger import GENESIS_HASH, LedgerEvent, compute_event_hash
from field_core.manifest import SEAL_ALGORITHMS
from field_core.signing import (
    generate_keypair,
    key_fingerprint,
    private_key_fingerprint,
    verify_event_signature,
)
from ledger_c2_support import KEY_PRIV, KEY_PUB, listing
from sealed_ledger.api import create_app, require_signing_from_env, signing_config_from_env
from sealed_ledger.bundle import verify_bundle
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import (
    REQUIRE_SIGNING_ENV,
    SIGN_KEY_ENV,
    LedgerStore,
    SigningConfig,
    SigningRequired,
    is_stop_type,
    load_signing_config,
)

runner = CliRunner()
FIXTURES = Path(__file__).resolve().parent / "fixtures"
PRE_F2_KEYS = {"event_id", "ts", "event_type", "agent_id", "payload", "prev_hash", "hash"}
STOP_TYPES = ["delegation.revoke", "kill.agent", "kill.domain", "kill.revive",
              "kill.drill.complete", "kill.endpoint_called", "lifecycle.decommissioned"]
NEAR_MISSES = ["kill", "kill.", "killed.agent", "lifecycle.decommission", "delegation.revoked",
               "delegation.mint", "registry.updated", "conformance.allow", "ledger.segment.rotated"]


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    """The per-event SIGN key pair (files) and a stranger's public key —
    separate from the C2 ANCHOR key (ledger_c2_support.KEY_PRIV/KEY_PUB)."""
    d = tmp_path_factory.mktemp("sign-keys")
    private_pem, public_pem = generate_keypair()
    _, stranger_pem = generate_keypair()
    priv, pub, stranger = d / "ledger-sign.pem", d / "ledger-sign.pub.pem", d / "stranger.pub.pem"
    priv.write_text(private_pem, encoding="ascii")
    pub.write_text(public_pem, encoding="ascii")
    stranger.write_text(stranger_pem, encoding="ascii")
    return {"priv": priv, "pub": pub, "stranger": stranger, "public_pem": public_pem,
            "private_pem": private_pem}


def _signed(tmp_path: Path, keys, require: bool = False, name: str = "events.jsonl") -> LedgerStore:
    return LedgerStore(tmp_path / name, signing=load_signing_config(keys["priv"], require))


def _lines(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def _relink(p: Path, idx: int, mutate) -> None:
    """The attacker without the key: mutate one field of line ``idx`` (its
    signature kept), rehash it, and recompute every later hash/prev_hash so
    the plain chain verifies again."""
    lines = p.read_text(encoding="utf-8").splitlines()
    recs = [json.loads(x) for x in lines]
    mutate(recs[idx])
    recs[idx]["hash"] = compute_event_hash(recs[idx])
    for k in range(idx + 1, len(recs)):
        recs[k]["prev_hash"] = recs[k - 1]["hash"]
        recs[k]["hash"] = compute_event_hash(recs[k])
    p.write_text("\n".join(json.dumps(r) for r in recs) + "\n", encoding="utf-8")


# ------------------------------------------------------------- key loading


@pytest.mark.parametrize("state", ["unset", "blank", "missing-file", "directory", "garbage",
                                   "not-ed25519", "public-key", "valid"])
@pytest.mark.parametrize("require", [False, True])
def test_load_signing_config_never_raises_and_reports_each_state(tmp_path, keys, state, require):
    """A missing, unreadable or malformed key is NEVER an exception (so never
    a process exit): ``signing: error`` with a one-line reason naming the
    failure class and the env var, never key material."""
    d = tmp_path / "keys"
    d.mkdir()
    path = {
        "unset": None, "blank": "  ", "missing-file": d / "absent.pem", "directory": d,
        "garbage": d / "garbage.pem", "not-ed25519": d / "ec.pem", "public-key": keys["pub"],
        "valid": keys["priv"],
    }[state]
    if state == "garbage":
        path.write_bytes(b"-----BEGIN PRIVATE KEY-----\nnot a key\n-----END PRIVATE KEY-----\n")
    if state == "not-ed25519":
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec

        path.write_bytes(ec.generate_private_key(ec.SECP256R1()).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
    cfg = load_signing_config(path, require_signing=require)
    assert cfg.require_signing is require
    if state in ("unset", "blank"):
        assert cfg.signing == "off" and cfg.key_error is None and cfg.key_fingerprint is None
    elif state == "valid":
        assert cfg.signing == "on" and cfg.key_error is None
        assert cfg.key_fingerprint == key_fingerprint(keys["public_pem"]) == private_key_fingerprint(keys["private_pem"])
        assert cfg.seal_algorithm == "ed25519-signed-chain"
    else:
        assert cfg.signing == "error" and cfg.key_fingerprint is None and cfg.private_key_pem is None
        assert cfg.key_error.startswith(("sign key unreadable", "sign key unusable"))
        assert SIGN_KEY_ENV in cfg.key_error
        assert "BEGIN" not in cfg.key_error and "not a key" not in cfg.key_error
        assert cfg.seal_algorithm == "sha-256-chain"
    # appendable is false EXACTLY when signing is required and no key is loaded
    assert cfg.appendable is (not require or state == "valid")
    assert "ed25519-signed-chain" in SEAL_ALGORITHMS and "sha-256-chain" in SEAL_ALGORITHMS


def test_require_signing_env_parsing(monkeypatch):
    for raw, want in {"1": True, "true": True, "YES": True, " on ": True, "0": False, "": False,
                      "no": False, "2": False, "enabled": False}.items():
        monkeypatch.setenv(REQUIRE_SIGNING_ENV, raw)
        assert require_signing_from_env() is want, raw
    monkeypatch.delenv(REQUIRE_SIGNING_ENV)
    assert require_signing_from_env() is False


# ------------------------------------------------------------- classifier


@pytest.mark.parametrize("event_type", STOP_TYPES)
def test_is_stop_type_each_class(event_type):
    assert is_stop_type(event_type) is True


@pytest.mark.parametrize("event_type", NEAR_MISSES)
def test_is_stop_type_near_misses_are_start_type(event_type):
    assert is_stop_type(event_type) is False


# ------------------------------------------------------- store-level policy


def test_key_loaded_every_append_is_signed_and_verifies(tmp_path, keys):
    s = _signed(tmp_path, keys)
    events = [s.append("action", {"n": i}, agent_id="a") for i in range(3)]
    for e in events:
        assert e.signature and e.signing_failed is None
        assert verify_event_signature(e, keys["public_pem"])
        assert compute_event_hash(e) == e.hash  # hash first, sign second
    assert s.verify().ok
    on_disk = _lines(s.path)
    assert all(set(rec) == PRE_F2_KEYS | {"signature"} for rec in on_disk)
    assert [r["signature"] for r in on_disk] == [e.signature for e in events]
    # a reopened store (same key) continues the chain, signed
    again = _signed(tmp_path, keys)
    e4 = again.append("action", {"n": 3})
    assert e4.prev_hash == events[-1].hash and verify_event_signature(e4, keys["public_pem"])
    assert LedgerStore(s.path).verify().ok  # a keyless reader still verifies the chain


def test_no_key_appends_unsigned_with_exactly_the_pre_f2_keys_on_disk(tmp_path):
    """Key unset (today's estates): the JSON line is byte-for-byte a pre-F2
    line — no ``signature`` key and no ``signing_failed`` key."""
    s = LedgerStore(tmp_path / "events.jsonl")
    e = s.append("registry.updated", {"n": 1}, agent_id="a")
    assert e.signature is None and e.signing_failed is None
    assert s.signing.signing == "off" and s.signing.appendable is True
    [rec] = _lines(s.path)
    assert set(rec) == PRE_F2_KEYS
    assert '"signature"' not in s.path.read_text(encoding="utf-8")
    assert '"signing_failed"' not in s.path.read_text(encoding="utf-8")


def test_require_signing_no_key_refuses_start_type_before_writing_anything(tmp_path):
    """The refusal branch (``LedgerStore._require_appendable``): nothing is
    written — not the open segment, not even the writer lock file."""
    s = LedgerStore(tmp_path / "events.jsonl", signing=SigningConfig(require_signing=True))
    assert s.signing.appendable is False
    before = listing(tmp_path)
    with pytest.raises(SigningRequired) as exc_info:
        s.append("registry.updated", {"n": 1}, agent_id="a")
    message = str(exc_info.value)
    assert REQUIRE_SIGNING_ENV in message and SIGN_KEY_ENV in message and "registry.updated" in message
    assert listing(tmp_path) == before and not s.path.exists()
    assert s.global_length() == 0


@pytest.mark.parametrize("event_type", STOP_TYPES)
def test_require_signing_no_key_accepts_stop_types_stamped_signing_failed(tmp_path, event_type):
    """The stamping branch: a stop-type event is written UNSIGNED with
    ``signing_failed: true`` inside its hash — the caller sends nothing new."""
    s = LedgerStore(tmp_path / "events.jsonl", signing=SigningConfig(require_signing=True))
    e = s.append(event_type, {"reason": "F2"}, agent_id="a")
    assert e.signing_failed is True and e.signature is None
    assert compute_event_hash(e) == e.hash
    [rec] = _lines(s.path)
    assert rec["signing_failed"] is True and "signature" not in rec
    assert set(rec) == PRE_F2_KEYS | {"signing_failed"}
    assert s.verify().ok and LedgerStore(s.path).verify().ok
    # removing the stamp from the line is a tamper, not a downgrade
    del rec["signing_failed"]
    s.path.write_text(json.dumps(rec) + "\n", encoding="utf-8")
    v = LedgerStore(s.path).verify()
    assert not v.ok and v.first_break_index == 0 and "mutated" in v.reason


def test_require_signing_with_an_error_key_behaves_as_no_key(tmp_path, keys):
    cfg = load_signing_config(tmp_path / "absent.pem", require_signing=True)
    assert cfg.signing == "error" and cfg.appendable is False
    s = LedgerStore(tmp_path / "events.jsonl", signing=cfg)
    with pytest.raises(SigningRequired) as exc_info:
        s.append("conformance.allow", {}, agent_id="a")
    assert "sign key unreadable" in str(exc_info.value)
    assert s.append("delegation.revoke", {}, agent_id="a").signing_failed is True


def test_require_signing_off_with_an_error_key_appends_unsigned_with_no_flag(tmp_path):
    """REQUIRE_SIGNING=0 and a key in error: appends are unsigned (no
    ``signing_failed`` key) and /health shows the error (the A7 soak check)."""
    cfg = load_signing_config(tmp_path / "absent.pem", require_signing=False)
    s = LedgerStore(tmp_path / "events.jsonl", signing=cfg)
    e = s.append("conformance.allow", {}, agent_id="a")
    assert e.signature is None and e.signing_failed is None
    [rec] = _lines(s.path)
    assert set(rec) == PRE_F2_KEYS
    health = TestClient(create_app(store=s)).get("/health").json()
    assert health["signing"] == "error" and health["appendable"] is True
    assert health["key_error"].startswith("sign key unreadable")


def test_hold_rotation_and_retention_are_refused_before_writing_when_not_appendable(tmp_path):
    """The other three append paths under the fail-closed policy: refused
    with nothing written or moved (no hold marker, no rename, no archive)."""
    from ledger_c2_support import fill, rotate

    p = tmp_path / "ledger" / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 3)
    rotate(s, "r1")
    fill(s, 2)
    s.signing = SigningConfig(require_signing=True)  # the fault state, flipped in place
    before = listing(tmp_path)
    with pytest.raises(SigningRequired):
        s.place_hold(by="GC", reason="litigation")
    assert not s.hold_path.exists()
    with pytest.raises(SigningRequired):
        s.rotate(private_key_pem=KEY_PRIV, operator="ops", reason="quarter")
    with pytest.raises(SigningRequired):
        s.archive_closed_segments(older_than_days=0, archive_dir=tmp_path / "archive",
                                  operator="ops", data_dir=tmp_path)
    assert listing(tmp_path) == before
    assert LedgerStore(p).verify().ok
    # release of a hold placed BEFORE the fault: the event comes first, so the
    # refusal leaves the hold in force
    s.signing = SigningConfig()
    s.place_hold(by="GC", reason="litigation")
    s.signing = SigningConfig(require_signing=True)
    with pytest.raises(SigningRequired):
        s.release_hold(by="GC")
    assert s.hold_path.exists()


# ------------------------------------------------------------------- API


def test_health_reports_signing_off_by_default_with_every_existing_field(tmp_path):
    client = TestClient(create_app(store=LedgerStore(tmp_path / "events.jsonl")))
    h = client.get("/health").json()
    for key in ("ok", "service", "version", "event_count", "head_hash", "earliest_live_index",
                "earliest_live_ts", "build_sha"):
        assert key in h, key
    assert h["appendable"] is True and h["signing"] == "off" and h["key_fingerprint"] is None
    assert h["seal_algorithm"] == "sha-256-chain" and h["require_signing"] is False
    assert "key_error" not in h


def test_health_signing_on_reports_the_keys_admin_fingerprint_and_signed_chain(tmp_path, keys):
    client = TestClient(create_app(store=_signed(tmp_path, keys)))
    h = client.get("/health").json()
    assert h["signing"] == "on" and h["appendable"] is True and h["require_signing"] is False
    assert h["key_fingerprint"] == key_fingerprint(keys["public_pem"])  # what keys-admin prints
    assert h["seal_algorithm"] == "ed25519-signed-chain" and "key_error" not in h
    assert h["seal_algorithm"] in SEAL_ALGORITHMS
    assert "BEGIN" not in json.dumps(h)


@pytest.mark.parametrize("require", [False, True])
def test_health_signing_error_reports_key_error_and_appendable_follows_the_flag(tmp_path, require):
    cfg = load_signing_config(tmp_path / "absent.pem", require_signing=require)
    client = TestClient(create_app(store=LedgerStore(tmp_path / "events.jsonl", signing=cfg)))
    h = client.get("/health").json()
    assert h["signing"] == "error" and h["require_signing"] is require
    assert h["appendable"] is (not require)
    assert h["key_error"].startswith("sign key unreadable") and SIGN_KEY_ENV in h["key_error"]
    assert h["seal_algorithm"] == "sha-256-chain" and h["key_fingerprint"] is None


def test_post_events_503_for_start_type_and_201_signing_failed_for_stop_type(tmp_path):
    """The served fault path (what signing_fault.py proves in CI): require
    signing, no key => registry.updated 503 naming the env var; kill.agent
    201 with signing_failed and NO signature key; GET /events shows it."""
    s = LedgerStore(tmp_path / "events.jsonl", signing=SigningConfig(require_signing=True))
    client = TestClient(create_app(store=s))
    assert client.get("/health").json()["appendable"] is False
    r = client.post("/events", json={"event_type": "registry.updated", "agent_id": "a", "payload": {}})
    assert r.status_code == 503, r.text
    assert REQUIRE_SIGNING_ENV in r.json()["detail"]
    assert client.get("/health").json()["event_count"] == 0
    r = client.post("/events", json={"event_type": "kill.agent", "agent_id": "a",
                                     "payload": {"reason": "F2 fault-path proof"}})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["signing_failed"] is True and "signature" not in body
    assert '"signature"' not in r.text
    [served] = client.get("/events", params={"event_type": "kill.agent"}).json()
    assert served == body and served["signing_failed"] is True and "signature" not in served
    v = client.get("/verify").json()
    assert v == {"ok": True, "length": 1, "first_break_index": None, "reason": None}


def test_served_app_builds_from_env_with_a_missing_key_never_a_process_exit(tmp_path, monkeypatch, keys):
    """The served store reads FIELD_LEDGER_SIGN_KEY / FIELD_LEDGER_REQUIRE_SIGNING
    once at start; a missing key still builds and serves."""
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv(SIGN_KEY_ENV, str(tmp_path / "keys" / "missing.pem"))
    monkeypatch.setenv(REQUIRE_SIGNING_ENV, "1")
    client = TestClient(create_app())
    h = client.get("/health").json()
    assert h["signing"] == "error" and h["appendable"] is False and h["require_signing"] is True
    assert client.post("/events", json={"event_type": "registry.updated"}).status_code == 503
    r = client.post("/events", json={"event_type": "kill.agent", "agent_id": "a"})
    assert r.status_code == 201 and r.json()["signing_failed"] is True
    # the key placed, require off: a new app signs (the A7 state)
    monkeypatch.setenv(SIGN_KEY_ENV, str(keys["priv"]))
    monkeypatch.setenv(REQUIRE_SIGNING_ENV, "0")
    client = TestClient(create_app())
    h = client.get("/health").json()
    assert h["signing"] == "on" and h["appendable"] is True and h["event_count"] == 1
    r = client.post("/events", json={"event_type": "conformance.allow", "agent_id": "a"})
    assert r.status_code == 201 and verify_event_signature(
        LedgerEvent.model_validate(r.json()), keys["public_pem"])
    assert signing_config_from_env().signing == "on"


def test_served_verify_and_events_routes_carry_signed_events_verbatim(tmp_path, keys):
    s = _signed(tmp_path, keys)
    e = s.append("action", {"n": 1}, agent_id="a")
    client = TestClient(create_app(store=s))
    v = client.get("/verify").json()
    assert v == {"ok": True, "length": 1, "first_break_index": None, "reason": None}
    [served] = client.get("/events").json()
    assert served["signature"] == e.signature
    assert verify_event_signature(LedgerEvent.model_validate(served), keys["public_pem"])


def test_anchor_key_is_never_used_for_events(tmp_path, keys, monkeypatch):
    """The anchor key (FIELD_LEDGER_ANCHOR_KEY) is a separate key: with only
    it configured, events are NOT signed, and a rotation's anchor is signed
    by it while the rotation event is signed by the sign key."""
    from ledger_c2_support import fill

    anchor = tmp_path / "anchor.pem"
    anchor.write_text(KEY_PRIV, encoding="ascii")
    monkeypatch.setenv("FIELD_LEDGER_ANCHOR_KEY", str(anchor))
    monkeypatch.delenv(SIGN_KEY_ENV, raising=False)
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    client = TestClient(create_app())
    assert client.get("/health").json()["signing"] == "off"
    r = client.post("/events", json={"event_type": "action"})
    assert r.status_code == 201 and "signature" not in r.json()
    # now both keys: the rotation event is signed with the SIGN key, its
    # anchor with the ANCHOR key
    s = _signed(tmp_path / "both", keys)
    fill(s, 2)
    client = TestClient(create_app(store=s))
    rot = client.post("/rotate", json={"operator": "ops", "reason": "q"}).json()
    ev = LedgerEvent.model_validate(rot["rotation_event"])
    assert verify_event_signature(ev, keys["public_pem"])
    assert not verify_event_signature(ev, KEY_PUB)
    from field_core.signing import verify_manifest

    a = dict(rot["anchor"])
    sig = a.pop("signature")
    assert verify_manifest(a, sig, KEY_PUB) and not verify_manifest(a, sig, keys["public_pem"])


# ------------------------------------------------------------ CLI verify


def _verify(*args: str):
    return runner.invoke(cli_app, ["verify", *args])


def test_cli_verify_event_pubkey_ok_and_prints_the_summary_line(tmp_path, keys):
    s = _signed(tmp_path, keys)
    for i in range(4):
        s.append("action", {"n": i}, agent_id="a")
    r = _verify("--path", str(s.path), "--event-pubkey", str(keys["pub"]))
    assert r.exit_code == 0, r.output
    assert r.stdout.splitlines() == [
        "OK — chain intact over 4 events",
        "signed 4 unsigned 0 first_unsigned_index none first_signing_failed_index none "
        "first_unsigned_after_signed none",
    ]
    # without the flag the output is exactly what it was before F2
    assert _verify("--path", str(s.path)).stdout.splitlines() == ["OK — chain intact over 4 events"]


def test_cli_verify_relinked_tamper_of_a_signed_event_fails_naming_the_index(tmp_path, keys):
    """THE F2 case (the anchor forgery test's stronger sibling): one field of
    a signed event is edited and every later hash recomputed by an attacker
    without the key. Plain verify passes (pinned); --event-pubkey names the
    index."""
    s = _signed(tmp_path, keys)
    for i in range(4):
        s.append("spend", {"amount": 100 + i}, agent_id="fin")
    _relink(s.path, 1, lambda rec: rec["payload"].update(amount=1))
    assert LedgerStore(s.path).verify().ok  # the plain chain is blind to it
    assert _verify("--path", str(s.path)).exit_code == 0
    r = _verify("--path", str(s.path), "--event-pubkey", str(keys["pub"]))
    assert r.exit_code == 1, r.output
    assert r.stdout.splitlines()[0] == "OK — chain intact over 4 events"
    assert r.stdout.splitlines()[1].startswith("SIGNATURE INVALID — index 1:")
    assert "signed " not in r.stdout  # no summary line on a failure


@pytest.mark.parametrize("field", ["agent_id", "event_type", "ts", "event_id"])
def test_cli_verify_every_relinked_field_edit_of_a_signed_event_is_named(tmp_path, keys, field):
    s = _signed(tmp_path, keys)
    for i in range(3):
        s.append("action", {"n": i}, agent_id="a")
    _relink(s.path, 2, lambda rec: rec.update({field: "x" if field != "ts" else "2020-01-01T00:00:00+00:00"}))
    assert LedgerStore(s.path).verify().ok
    r = _verify("--path", str(s.path), "--event-pubkey", str(keys["pub"]))
    assert r.exit_code == 1 and "SIGNATURE INVALID — index 2:" in r.stdout


def test_cli_verify_a_stripped_signature_is_reported_at_the_tail_and_failed_elsewhere(tmp_path, keys):
    """The honest limit: an attacker who also DROPS the signature of the event
    they edited leaves an unsigned event in signed territory. Mid-chain that
    still fails: the next event's prev_hash is under ITS signature, so the
    re-link invalidates it (named at that index). Only a TAIL edit is silent
    — reported (`first_unsigned_after_signed`, the unsigned count), never
    failed, since pre-F2 history and stop-type events are legal unsigned; the
    operator compares the unsigned count with the pre-F2 count (A7 soak)."""
    s = _signed(tmp_path, keys)
    for i in range(4):
        s.append("action", {"n": i}, agent_id="a")

    def strip_and_edit(rec):
        rec.pop("signature")
        rec["payload"]["n"] = 99

    _relink(s.path, 2, strip_and_edit)  # mid-chain: index 3's prev_hash moved under its signature
    r = _verify("--path", str(s.path), "--event-pubkey", str(keys["pub"]))
    assert r.exit_code == 1 and "SIGNATURE INVALID — index 3:" in r.stdout
    s = _signed(tmp_path / "tail", keys)
    for i in range(4):
        s.append("action", {"n": i}, agent_id="a")
    _relink(s.path, 3, strip_and_edit)  # the tail: nothing after it to re-link
    assert LedgerStore(s.path).verify().ok
    r = _verify("--path", str(s.path), "--event-pubkey", str(keys["pub"]))
    assert r.exit_code == 0, r.output
    assert r.stdout.splitlines()[-1] == (
        "signed 3 unsigned 1 first_unsigned_index 3 first_signing_failed_index none "
        "first_unsigned_after_signed 3")


def test_cli_verify_wrong_event_pubkey_exit_1_naming_index_0(tmp_path, keys):
    s = _signed(tmp_path, keys)
    s.append("action", {"n": 0})
    r = _verify("--path", str(s.path), "--event-pubkey", str(keys["stranger"]))
    assert r.exit_code == 1 and "SIGNATURE INVALID — index 0:" in r.stdout
    # the ANCHOR public key is not the sign key either
    anchor_pub = tmp_path / "anchor.pub.pem"
    anchor_pub.write_text(KEY_PUB, encoding="ascii")
    r = _verify("--path", str(s.path), "--event-pubkey", str(anchor_pub))
    assert r.exit_code == 1 and "SIGNATURE INVALID — index 0:" in r.stdout


def test_cli_verify_pre_f2_fixture_verifies_with_the_unsigned_count(tmp_path, keys):
    """The scene4 fixture (2026-08-10): 5 unsigned events verify, reported."""
    p = tmp_path / "events.jsonl"
    p.write_bytes((FIXTURES / "scene4" / "events.jsonl").read_bytes())
    r = _verify("--path", str(p), "--event-pubkey", str(keys["pub"]))
    assert r.exit_code == 0, r.output
    assert r.stdout.splitlines() == [
        "OK — chain intact over 5 events",
        "signed 0 unsigned 5 first_unsigned_index 0 first_signing_failed_index none "
        "first_unsigned_after_signed none",
    ]


def test_cli_verify_mixed_history_reports_every_index(tmp_path, keys):
    """pre-F2 (3 unsigned) -> key on (2 signed) -> require+no key (1 stop-type
    stamped) -> key on (1 signed)."""
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    for i in range(3):
        s.append("action", {"n": i})
    s = _signed(tmp_path, keys)
    s.append("action", {"n": 3})
    s.append("action", {"n": 4})
    s = LedgerStore(p, signing=SigningConfig(require_signing=True))
    s.append("kill.agent", {"reason": "x"}, agent_id="a")
    s = _signed(tmp_path, keys)
    s.append("action", {"n": 6})
    r = _verify("--path", str(p), "--event-pubkey", str(keys["pub"]))
    assert r.exit_code == 0, r.output
    assert r.stdout.splitlines()[-1] == (
        "signed 3 unsigned 4 first_unsigned_index 0 first_signing_failed_index 5 "
        "first_unsigned_after_signed 5")


def test_cli_verify_event_pubkey_must_be_an_ed25519_public_key(tmp_path, keys):
    s = _signed(tmp_path, keys)
    s.append("action")
    garbage = tmp_path / "garbage.pem"
    garbage.write_text("not a key", encoding="ascii")
    for bad in (keys["priv"], garbage, tmp_path / "absent.pem"):
        r = _verify("--path", str(s.path), "--event-pubkey", str(bad))
        assert r.exit_code == 2, r.output
        assert "--event-pubkey is not a readable Ed25519 public key" in r.output
        assert "BEGIN" not in r.output


def test_cli_verify_event_pubkey_across_rotation_closed_archived_and_genesis_modes(tmp_path, keys):
    """Rotation with signed events in the open segment still verifies; the
    rotation events are signed too; every verify mode checks signatures."""
    from ledger_c2_support import fill, rotate

    p = tmp_path / "ledger" / "events.jsonl"
    s = _signed(tmp_path / "ledger", keys)
    fill(s, 4)
    r1 = rotate(s, "r1")
    fill(s, 3)
    r2 = rotate(s, "r2")
    fill(s, 2)
    for rot in (r1, r2):
        assert rot.rotation_event.signature and verify_event_signature(rot.rotation_event, keys["public_pem"])
    assert LedgerStore(p).verify().ok
    anchors = tmp_path / "anchors.jsonl"
    anchor_pub = tmp_path / "anchor.pub.pem"
    anchor_pub.write_text(KEY_PUB, encoding="ascii")
    from sealed_ledger.anchors import write_anchor

    write_anchor(s, anchors, private_key_pem=KEY_PRIV)
    # whole ledger, with the ANCHOR key on --pubkey and the SIGN key on --event-pubkey
    r = _verify("--path", str(p), "--anchors", str(anchors), "--pubkey", str(anchor_pub),
                "--event-pubkey", str(keys["pub"]))
    assert r.exit_code == 0, r.output
    assert r.stdout.splitlines() == [
        "OK — chain intact over 11 events",
        "(3 segments, 0 archived; 11 events hash-verified)",
        "signed 11 unsigned 0 first_unsigned_index none first_signing_failed_index none "
        "first_unsigned_after_signed none",
        "OK — 1 anchor(s) hold (1 signature(s) verified)",
    ]
    # a live closed segment
    r = _verify("--path", str(p.with_name("events-2.jsonl")), "--event-pubkey", str(keys["pub"]))
    assert r.exit_code == 0 and r.stdout.splitlines()[-1].startswith("signed 4 unsigned 0")
    # --genesis mode (the file alone): indices are local to the file
    r = _verify("--path", str(p.with_name("events-2.jsonl")), "--genesis", r1.head_hash,
                "--event-pubkey", str(keys["pub"]))
    assert r.exit_code == 0 and r.stdout.splitlines()[-1].startswith("signed 4 unsigned 0")
    # an archived segment from its sidecar (the test stand-in has no sidecar:
    # use the real retention apply, days 0, on the same filesystem)
    res = s.archive_closed_segments(older_than_days=0, archive_dir=tmp_path / "archive",
                                    operator="ops", data_dir=tmp_path)
    assert res["archived_segments"] == [1, 2]
    r = _verify("--path", str(tmp_path / "archive" / "events-1.jsonl"), "--pubkey", str(anchor_pub),
                "--event-pubkey", str(keys["pub"]))
    assert r.exit_code == 0, r.output
    assert r.stdout.splitlines()[-1] == (
        "signed 4 unsigned 0 first_unsigned_index none first_signing_failed_index none "
        "first_unsigned_after_signed none")
    # the live walk after archival: 4 live events (the rotation event, two
    # fills, the retention event), every one signed
    r = _verify("--path", str(p), "--event-pubkey", str(keys["pub"]))
    assert r.exit_code == 0, r.output
    assert r.stdout.splitlines()[-1].startswith("signed 4 unsigned 0")
    # a relinked edit inside a closed segment moves its head: the journal
    # catches it before any signature is read (chain walk first)
    s2 = _signed(tmp_path / "two", keys)
    fill(s2, 4)
    rotate(s2, "r1")
    fill(s2, 2)
    _relink(s2.path.with_name("events-1.jsonl"), 2, lambda rec: rec["payload"].update(n=99))
    r = _verify("--path", str(s2.path.with_name("events-1.jsonl")), "--event-pubkey", str(keys["pub"]))
    assert r.exit_code == 1 and r.stdout.startswith("TAMPERED — segment 1: head")
    assert "signed " not in r.stdout


def test_journal_and_reconcile_carry_the_signed_rotation_event(tmp_path, keys):
    """The intent journals the rotation event with its signature; recovery
    re-installs exactly that event."""
    from ledger_c2_support import fill, journal_records, rotate

    s = _signed(tmp_path, keys)
    fill(s, 2)
    rot = rotate(s, "r1")
    intent = next(r for r in journal_records(s.path) if r["op"] == "rotate-intent")
    assert intent["rotation_event"]["signature"] == rot.rotation_event.signature
    assert LedgerEvent.model_validate(intent["rotation_event"]) == rot.rotation_event
    assert LedgerStore(s.path).verify().ok


# ---------------------------------------------------------------- export


def test_verify_export_passes_on_a_bundle_carrying_signed_events(tmp_path, keys):
    """C1 bundles carry events verbatim (the signature included); an unsigned
    served-style bundle and a --sign-key bundle both verify; the event lines
    still hold no key outside LedgerEvent's."""
    s = _signed(tmp_path, keys)
    for i in range(3):
        s.append("action", {"n": i}, agent_id="a")
    export_priv, export_pub = generate_keypair()
    (tmp_path / "export.pem").write_text(export_priv, encoding="ascii")
    (tmp_path / "export.pub.pem").write_text(export_pub, encoding="ascii")
    unsigned = Path(s.export(tmp_path / "exports").bundle_dir)
    signed = Path(s.export(tmp_path / "exports", private_key_pem=export_priv).bundle_dir)
    for bundle in (unsigned, signed):
        lines = _lines(bundle / "events.jsonl")
        assert lines == _lines(s.path)  # verbatim, signature included
        assert all(set(rec) <= set(LedgerEvent.model_fields) for rec in lines)
        assert all("signature" in rec and "signing_failed" not in rec for rec in lines)
    assert verify_bundle(unsigned).ok
    assert verify_bundle(signed, public_key_pem=export_pub).ok
    r = runner.invoke(cli_app, ["verify-export", str(signed), "--pubkey", str(tmp_path / "export.pub.pem")])
    assert r.exit_code == 0, r.output
    assert "signature valid" in r.stdout
    r = runner.invoke(cli_app, ["verify-export", str(unsigned)])
    assert r.exit_code == 0 and "spine unverified (unsigned)" in r.stdout
    # an edited signed event in the copy still fails verify-export (hash) at its index
    lines = (signed / "events.jsonl").read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[1])
    rec["payload"]["n"] = 42
    lines[1] = json.dumps(rec)
    (signed / "events.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    v = verify_bundle(signed, public_key_pem=export_pub)
    assert not v.ok and v.first_failing_index == 1


def test_served_export_of_a_stamped_stop_event_verifies(tmp_path):
    s = LedgerStore(tmp_path / "events.jsonl", signing=SigningConfig(require_signing=True))
    s.append("kill.agent", {"reason": "x"}, agent_id="a")
    client = TestClient(create_app(store=s))
    r = client.post("/export", params={"out_dir": str(tmp_path / "exports")})
    assert r.status_code == 200
    bundle = Path(r.json()["bundle_dir"])
    [rec] = _lines(bundle / "events.jsonl")
    assert rec["signing_failed"] is True and "signature" not in rec
    assert verify_bundle(bundle).ok


# ------------------------------------------------------------- CLI append


def test_cli_append_signs_with_the_env_key_and_refuses_when_required_without_one(tmp_path, keys, monkeypatch):
    p = tmp_path / "events.jsonl"
    monkeypatch.setenv(SIGN_KEY_ENV, str(keys["priv"]))
    monkeypatch.delenv(REQUIRE_SIGNING_ENV, raising=False)
    r = runner.invoke(cli_app, ["append", "action", "--path", str(p), "--payload", '{"n": 1}'])
    assert r.exit_code == 0, r.output
    ev = LedgerEvent.model_validate(json.loads(r.stdout.strip()))
    assert verify_event_signature(ev, keys["public_pem"])
    monkeypatch.delenv(SIGN_KEY_ENV)
    monkeypatch.setenv(REQUIRE_SIGNING_ENV, "1")
    r = runner.invoke(cli_app, ["append", "registry.updated", "--path", str(p)])
    assert r.exit_code == 2 and "append refused" in r.output and REQUIRE_SIGNING_ENV in r.output
    assert len(_lines(p)) == 1
    r = runner.invoke(cli_app, ["append", "kill.agent", "--path", str(p), "--agent-id", "a"])
    assert r.exit_code == 0 and json.loads(r.stdout.strip())["signing_failed"] is True
    monkeypatch.setenv(REQUIRE_SIGNING_ENV, "0")
    r = runner.invoke(cli_app, ["append", "registry.updated", "--path", str(p)])
    assert r.exit_code == 0 and "signature" not in json.loads(r.stdout.strip())
    r = _verify("--path", str(p), "--event-pubkey", str(keys["pub"]))
    assert r.exit_code == 0 and r.stdout.splitlines()[-1] == (
        "signed 1 unsigned 2 first_unsigned_index 1 first_signing_failed_index 1 "
        "first_unsigned_after_signed 1")


def test_unsigned_line_has_exactly_the_pre_f2_keys_and_signed_lines_no_extra_keys(tmp_path, keys):
    """The bundle 'pure event lines' intent, restated for F2: an unsigned line
    is the 7 pre-F2 keys; a signed line adds only ``signature``; no line ever
    holds a key outside LedgerEvent's fields."""
    s = LedgerStore(tmp_path / "events.jsonl")
    s.append("action", {"n": 0})
    s = _signed(tmp_path, keys)
    s.append("action", {"n": 1})
    plain, signed = _lines(s.path)
    assert set(plain) == PRE_F2_KEYS
    assert set(signed) == PRE_F2_KEYS | {"signature"}
    assert set(plain) <= set(LedgerEvent.model_fields) and set(signed) <= set(LedgerEvent.model_fields)
    assert GENESIS_HASH == plain["prev_hash"]


def test_signing_config_repr_never_shows_key_material(keys):
    """Reviewer pin (F2 rule 5, key material never reaches /health or logs):
    a loaded ``SigningConfig`` formatted into any message — repr, str, an
    f-string, a log line, an exception — discloses its state and fingerprint,
    never the private key. Delete ``repr=False`` on ``private_key_pem`` and
    this fails."""
    cfg = load_signing_config(keys["priv"], True)
    assert cfg.signing == "on" and cfg.private_key_pem is not None
    secret_fragment = keys["private_pem"].strip().splitlines()[1][:16]
    for text in (repr(cfg), str(cfg), f"{cfg}", f"{cfg!r}"):
        assert "PRIVATE KEY" not in text and "BEGIN" not in text
        assert secret_fragment not in text
        assert cfg.key_fingerprint in text and "require_signing=True" in text
