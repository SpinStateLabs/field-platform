"""C2 hardening after adversarial review: guards whose removal no earlier test
detected, forged journal records, partial retention runs, and the served
lanes that keep /health and appends off the heavy-read queue.

Each test names the review finding it answers (C2R-*, C2PD-*, CLM-*, C4R-5).
"""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import shutil
import socket
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from field_core.ledger import GENESIS_HASH, compute_event_hash, make_event
from ledger_c2_support import (
    KEY_PRIV,
    KEY_PUB,
    archive_oldest_for_test,
    edit_line,
    fill,
    journal_records,
    listing,
    pre_c2_anchor_line,
    rotate,
    three_segments,
)
from sealed_ledger import store as store_mod
from sealed_ledger.anchors import verify_anchors
from sealed_ledger.api import create_app, load_anchor_key
from sealed_ledger.bundle import verify_bundle
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import (
    JOURNAL_FORMAT,
    LedgerBusy,
    LedgerCorrupt,
    LedgerStore,
    LegalHoldActive,
    NoAnchorKey,
    RotationRefused,
    closed_path_for,
    journal_line,
    journal_path_for,
    sidecar_path_for,
    verify_segment_file,
)

runner = CliRunner()
FUTURE = datetime.now(timezone.utc) + timedelta(days=3650)  # every closed segment is "old"


@pytest.fixture(autouse=True)
def env(monkeypatch, tmp_path):
    for name in ("FIELD_LEDGER_URL", "FIELD_SHARED_SECRET", "FIELD_LEDGER_RETENTION_DAYS",
                 "FIELD_LEDGER_ARCHIVE_DIR", "FIELD_LEDGER_CRASH_AT", "FIELD_LEDGER_ANCHOR_KEY",
                 "FIELD_LEDGER_READ_CONCURRENCY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    return monkeypatch


# ------------------------------------------------------------------ helpers


def _archived_ledger(tmp_path: Path):
    """data/ledger with three segments; segments 1 and 2 archived by the REAL
    retention apply (so a ledger.retention.applied event names them)."""
    data = tmp_path / "data"
    s, p, hashes = three_segments(data / "ledger")
    r = _apply(s, data)
    assert r["archived_segments"] == [1, 2]
    return data, s, p, hashes


def _apply(s: LedgerStore, data: Path, **kw):
    return s.archive_closed_segments(
        older_than_days=kw.pop("days", 1), archive_dir=kw.pop("adir", data / "ledger-archive"),
        operator=kw.pop("operator", "ops"), data_dir=data, now=kw.pop("now", FUTURE), **kw,
    )


def _append_journal(p: Path, rec: dict | bytes) -> None:
    with open(journal_path_for(p), "ab") as fh:
        fh.write(rec if isinstance(rec, bytes) else journal_line(rec))


def _rewrite_journal(p: Path, edit) -> None:
    """Apply ``edit(rec)`` to every record, keeping the writer's line format."""
    recs = journal_records(p)
    for rec in recs:
        edit(rec)
    journal_path_for(p).write_bytes(b"".join(journal_line(rec) for rec in recs))


def _rewrite_from(path: Path, k: int, fn) -> list[str]:
    """Edit event k of a file, re-hash it and re-link + re-hash every later
    event IN THAT FILE (a self-consistent rewrite)."""
    recs = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    fn(recs[k])
    recs[k]["hash"] = compute_event_hash(recs[k])
    for j in range(k + 1, len(recs)):
        recs[j]["prev_hash"] = recs[j - 1]["hash"]
        recs[j]["hash"] = compute_event_hash(recs[j])
    path.write_text("".join(json.dumps(r) + "\n" for r in recs), encoding="utf-8")
    return [r["hash"] for r in recs]


def _forged_archive(p: Path, n: int, sha256: str) -> dict:
    file = f"events-{n}.jsonl"
    nowhere = p.parent.parent / "nowhere"
    return {"op": "archive", "n": n, "file": file, "archived_to": str(nowhere / file),
            "sidecar": str(nowhere / f"{file}.segment.json"), "sha256": sha256,
            "at": "2026-09-13T00:00:00+00:00", "operator": "attacker"}


def _pending_rotation(store: LedgerStore, installed: bool) -> dict:
    """A rotation stopped right after its rename (and, if ``installed``, after
    the new open segment is in place) — what a kill at rotate.after_rename /
    rotate.after_segment_created leaves, built in-process."""
    with store._writer():
        store._ensure_fresh_locked()
        plan = store._plan_rotation_locked(KEY_PRIV, "tester", "stopped mid-rotation")
        store._journal_append_locked(plan["intent"])
        store._write_rotating_tmp_locked(plan["rot"])
        store._rename_with_retry(store.path, plan["closed"])
        if installed:
            store._install_open_segment_locked()
    return plan


def _hand_chained(p: Path, n: int, pad: int = 0) -> list[str]:
    """``n`` events written in one go (no fsync per event), pre-C2 bytes."""
    p.parent.mkdir(parents=True, exist_ok=True)
    prev, hashes = GENESIS_HASH, []
    with open(p, "w", encoding="utf-8") as fh:
        for i in range(n):
            e = make_event("action", {"i": i, "pad": "x" * pad}, prev_hash=prev, agent_id=f"a{i % 3}")
            fh.write(e.model_dump_json() + "\n")
            prev = e.hash
            hashes.append(e.hash)
    return hashes


def _serve(app, graceful: float | None = None):
    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    # "critical": the graceful-shutdown cancellation of reads still queued is expected, not news
    config = uvicorn.Config(app, log_level="critical", timeout_graceful_shutdown=graceful)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    return server, thread, port


def _req(port: int, method: str, path: str, body=None, timeout: float = 5.0):
    t0 = time.monotonic()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        headers = {"content-type": "application/json"} if body is not None else {}
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return time.monotonic() - t0, resp.status, data
    except Exception as exc:  # noqa: BLE001
        return time.monotonic() - t0, type(exc).__name__, b""


# ------------------------------------ C2R-1 / CLM-4: forged journal archive op


def test_forged_archive_op_over_a_deleted_segment_is_a_break_and_apply_will_not_launder_it(tmp_path):
    s, p, hashes = three_segments(tmp_path / "ledger")
    closed_path_for(p, 1).unlink()
    _append_journal(p, _forged_archive(p, 1, "0" * 64))
    v = LedgerStore(p).verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == (1, 0), v
    assert "no ledger.retention.applied event in the live chain names it" in v.reason
    r = runner.invoke(cli_app, ["verify", "--path", str(p)])
    assert r.exit_code == 1 and r.stdout.startswith("TAMPERED — segment 1: journaled as archived to ")
    # archiving segment 2 behind a GENUINE retention event would hide the forgery: refused
    journal_before = journal_path_for(p).read_bytes()
    with pytest.raises(LedgerCorrupt, match=r"segment 1 does not verify against the journal; not archived "
                                            r"\(journaled as archived"):
        _apply(LedgerStore(p), tmp_path, adir=tmp_path / "archive")
    assert journal_path_for(p).read_bytes() == journal_before
    assert not sidecar_path_for(tmp_path / "archive" / "events-2.jsonl").exists()
    assert "ledger.retention.applied" not in [e.event_type for e in LedgerStore(p).events()]


def test_forged_archive_ops_cannot_hide_segments_still_in_the_ledger_directory(tmp_path):
    # a mutation (not re-hashed) inside segment 2, both segments "archived" by forged ops
    s, p, hashes = three_segments(tmp_path / "one" / "ledger")
    edit_line(closed_path_for(p, 2), 2, lambda rec: rec["payload"].update(tampered=True))
    for n in (1, 2):
        digest = hashlib.sha256(closed_path_for(p, n).read_bytes()).hexdigest()
        _append_journal(p, _forged_archive(p, n, digest))
    v = LedgerStore(p).verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == (2, 6), v
    assert v.reason.startswith("segment 2: archived segment (events-2.jsonl): hash mismatch at index 6:")
    # a retention event appended through the API does not change that: files still here are read
    LedgerStore(p).append("ledger.retention.applied", {"archived_segments": [1, 2]})
    v = LedgerStore(p).verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == (2, 6)
    # intact bytes, but not the ones the op journaled
    s, p, hashes = three_segments(tmp_path / "two" / "ledger")
    _append_journal(p, _forged_archive(p, 1, "0" * 64))
    v = LedgerStore(p).verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == (1, 0)
    assert v.reason == ("segment 1: archived segment (events-1.jsonl): file bytes differ from the "
                        "sha256 journaled at archival")


def test_an_archived_file_still_in_the_ledger_dir_rewritten_inside_itself_breaks_at_its_head(tmp_path):
    """REG: the head check in ``_closed_bytes_problem``. Segment 1 is rewritten
    inside itself (same count, re-hashed and re-linked from GENESIS, only its
    head moves) and a forged archive op journals the NEW sha-256, so the chain,
    the count and the digest all pass: only the journal's head_hash catches it."""
    s, p, hashes = three_segments(tmp_path / "ledger")
    seg1 = closed_path_for(p, 1)
    new_hashes = _rewrite_from(seg1, 1, lambda rec: rec["payload"].update(forged=True))
    assert new_hashes[0] == hashes[0] and new_hashes[-1] != hashes[3]
    _append_journal(p, _forged_archive(p, 1, hashlib.sha256(seg1.read_bytes()).hexdigest()))
    v = LedgerStore(p).verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == (1, 3), v
    assert v.reason == (f"segment 1: archived segment (events-1.jsonl): head {new_hashes[-1][:12]}… "
                        f"does not match the journal's head_hash {hashes[3][:12]}…")


@pytest.mark.parametrize("seg2", ["left-in-the-ledger-dir", "moved-to-its-archived_to"])
def test_every_archived_entry_needs_its_own_evidence_two_forged_lines(tmp_path, seg2):
    """C2R-1/CLM-4 residual: evidence for the NEWEST archived entry must not
    excuse an older one. Line 1 forges segment 1 over a deleted file; line 2
    carries the REAL sha-256 of the intact events-2.jsonl. No retention event."""
    s, p, hashes = three_segments(tmp_path / "ledger")
    closed_path_for(p, 1).unlink()
    _append_journal(p, _forged_archive(p, 1, "0" * 64))
    seg2_path = closed_path_for(p, 2)
    rec2 = _forged_archive(p, 2, hashlib.sha256(seg2_path.read_bytes()).hexdigest())
    if seg2 == "moved-to-its-archived_to":
        dst = Path(rec2["archived_to"])
        dst.parent.mkdir(parents=True)
        shutil.move(str(seg2_path), str(dst))
    _append_journal(p, rec2)
    v = LedgerStore(p).verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == (1, 0), v
    assert "no ledger.retention.applied event in the live chain names it (segment 1 with sha256 " in v.reason
    r = runner.invoke(cli_app, ["verify", "--path", str(p)])
    assert r.exit_code == 1 and r.stdout.startswith("TAMPERED — segment 1: journaled as archived to ")
    # an event naming the segments WITHOUT their digests (the pre-fix payload) is not evidence
    LedgerStore(p).append("ledger.retention.applied", {"archived_segments": [1, 2], "completed_moves": []})
    v = LedgerStore(p).verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == (1, 0), v


def test_bytes_only_evidence_is_never_promoted_by_a_later_apply(tmp_path):
    """A forged archive line whose file is intact verifies from its bytes, but
    a later genuine apply must not turn it into event evidence: once the file
    is deleted the entry is a break again."""
    data = tmp_path / "data"
    s, p, hashes = three_segments(data / "ledger")
    _append_journal(p, _forged_archive(p, 1, hashlib.sha256(closed_path_for(p, 1).read_bytes()).hexdigest()))
    assert LedgerStore(p).verify().ok  # bytes still here and matching: a pending move
    r = _apply(LedgerStore(p), data)
    assert r["archived_segments"] == [2]
    closed_path_for(p, 1).unlink()
    v = LedgerStore(p).verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == (1, 0), v
    assert "no ledger.retention.applied event in the live chain names it" in v.reason
    applied = [e for e in LedgerStore(p).events() if e.event_type == "ledger.retention.applied"]
    assert [x["n"] for x in applied[-1].payload["archive_evidence"]] == [2]


def test_retention_events_carry_every_evidenced_archive_forward(tmp_path):
    """Run 1 archives segments 1-2; its event is in segment 3. After a rotation
    run 2 archives segment 3 (the one holding run 1's event): its own event
    names 1, 2 and 3 with their digests, so the archive dir can go."""
    data = tmp_path / "data"
    s, p, hashes = three_segments(data / "ledger")
    first = _apply(s, data)
    assert first["archived_segments"] == [1, 2]
    fill(s, 1, "more")
    rotate(s, "r3")
    assert _apply(LedgerStore(p), data)["archived_segments"] == [3]
    applied = [e for e in LedgerStore(p).events() if e.event_type == "ledger.retention.applied"]
    assert len(applied) == 1  # run 1's event is archived with segment 3
    js = store_mod.parse_journal(journal_path_for(p).read_bytes())
    assert applied[0].payload["archive_evidence"] == [
        {"n": e["n"], "sha256": e["archived_sha256"]} for e in js.closed if e.get("archived_to")
    ]
    shutil.rmtree(data / "ledger-archive")
    v = LedgerStore(p).verify()
    assert v.ok and v.archived_segments == 3, v


def test_forged_archive_op_plus_a_forged_retention_event_is_the_documented_limit(tmp_path):
    """NOT detected (README journal row, LIMITS): whoever can append to the
    journal AND append a correctly linked ``ledger.retention.applied`` event
    whose ``archive_evidence`` names that segment number with the sha-256 the
    forged line journals (any API client can post that event type) hides a
    deleted oldest live segment from plain verify — the same power as the
    documented re-link blind spot. An anchor over the hidden range still fails
    explicitly."""
    s, p, hashes = three_segments(tmp_path / "ledger")
    (tmp_path / "anchors.jsonl").write_text(pre_c2_anchor_line(3, hashes[2]), encoding="utf-8")
    closed_path_for(p, 1).unlink()
    _append_journal(p, _forged_archive(p, 1, "0" * 64))
    LedgerStore(p).append("ledger.retention.applied", {"archive_evidence": [{"n": 1, "sha256": "1" * 64}]})
    assert not LedgerStore(p).verify().ok  # a digest other than the journaled one is not evidence
    LedgerStore(p).append("ledger.retention.applied", {"archive_evidence": [{"n": 1, "sha256": "0" * 64}]})
    v = LedgerStore(p).verify()
    assert v.ok and v.archived_segments == 1  # the limit, pinned
    r = verify_anchors(LedgerStore(p), tmp_path / "anchors.jsonl", public_key_pem=KEY_PUB)
    assert not r.ok and "is in archived segment 1" in r.first_failure


def test_an_archival_whose_event_never_landed_is_verified_from_its_archive_copy(tmp_path):
    s, p, hashes = three_segments(tmp_path / "ledger")
    arch = tmp_path / "archive"
    archive_oldest_for_test(s, arch)  # journal op + move, and no retention event (a run killed before it)
    v = LedgerStore(p).verify()
    assert v.ok and v.archived_segments == 1 and v.length == 11
    copy = arch / "events-1.jsonl"
    original = copy.read_bytes()
    edit_line(copy, 1, lambda rec: rec["payload"].update(n=7))
    v = LedgerStore(p).verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == (1, 1)
    assert v.reason.startswith("segment 1: archived segment (events-1.jsonl): hash mismatch at index 1:")
    copy.write_bytes(original)
    assert LedgerStore(p).verify().ok
    copy.unlink()
    v = LedgerStore(p).verify()
    assert not v.ok and "neither events-1.jsonl nor the archive copy is present" in v.reason
    # after a COMPLETED apply the event is the evidence: the archive dir is the operator's
    data, s2, p2, _ = _archived_ledger(tmp_path / "completed")
    shutil.rmtree(data / "ledger-archive")
    v = LedgerStore(p2).verify()
    assert v.ok and v.archived_segments == 2


# ----------------------------------- C2R-5: a journal error after the walk


def test_a_bad_journal_line_does_not_hide_an_earlier_break(tmp_path):
    s, p, hashes = three_segments(tmp_path / "one")
    edit_line(closed_path_for(p, 1), 2, lambda rec: rec["payload"].update(x=1))
    _append_journal(p, b'{"op":"bogus"}\n')
    v = LedgerStore(p).verify()
    assert (v.ok, v.break_segment, v.first_break_index) == (False, 1, 2), v
    assert v.reason.startswith("segment 1: hash mismatch at index 2:")
    # a break at or after the segment the journal can no longer describe names the journal line
    s, p, hashes = three_segments(tmp_path / "two")
    edit_line(p, 1, lambda rec: rec["payload"].update(x=1))
    _append_journal(p, b'{"op":"bogus"}\n')
    v = LedgerStore(p).verify()
    assert (v.ok, v.break_segment, v.first_break_index) == (False, 3, 8), v
    assert v.reason == "segment 3: segments journal line 5 invalid: unknown op 'bogus'"


# ------------------------------------------- C2R-6: journal record schema

_RECORDS = {
    "rotate-intent": {"op": "rotate-intent", "format": JOURNAL_FORMAT, "n": 3, "file": "events-3.jsonl",
                      "start_index": 8, "end_index": 10, "genesis_prev_hash": "a" * 64,
                      "head_hash": "b" * 64, "anchor": {}, "rotation_event": {"hash": "c" * 64},
                      "at": "2026-09-13T00:00:00+00:00"},
    "rotate-commit": {"op": "rotate-commit", "n": 3, "rotation_event_hash": "c" * 64,
                      "closed_at": "2026-09-13T00:00:00+00:00"},
    "rotate-abort": {"op": "rotate-abort", "n": 3},
    "archive": {"op": "archive", "n": 1, "file": "events-1.jsonl", "archived_to": "x", "sidecar": "y",
                "sha256": "d" * 64, "at": "2026-09-13T00:00:00+00:00"},
}
_SCHEMA_CASES = [
    *[("rotate-intent", k, None) for k in ("format", "n", "file", "start_index", "end_index",
                                           "genesis_prev_hash", "head_hash", "anchor", "rotation_event")],
    *[("rotate-commit", k, None) for k in ("n", "rotation_event_hash", "closed_at")],
    ("rotate-abort", "n", None),
    *[("archive", k, None) for k in ("n", "file", "archived_to", "sidecar", "sha256", "at")],
    ("rotate-intent", "n", "3"), ("rotate-intent", "n", True), ("rotate-intent", "head_hash", 7),
    ("rotate-intent", "rotation_event", {"no": "hash"}), ("archive", "file", "../elsewhere/events-1.jsonl"),
]


@pytest.mark.parametrize("op,key,bad", _SCHEMA_CASES)
def test_a_journal_record_missing_a_field_is_a_break_never_a_crash(tmp_path, op, key, bad):
    s, p, hashes = three_segments(tmp_path / "ledger")
    rec = json.loads(json.dumps(_RECORDS[op]))
    if bad is None:
        rec.pop(key)
    else:
        rec[key] = bad
    _append_journal(p, rec)
    store = LedgerStore(p)  # construction never raises
    v = store.verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == (3, 8), v
    assert v.reason.startswith("segment 3: segments journal line 5 invalid: ")
    client = TestClient(create_app(store=store), raise_server_exceptions=False)
    served = client.get("/verify")
    assert served.status_code == 200 and served.json()["ok"] is False
    r = client.post("/events", json={"event_type": "x"})
    assert r.status_code == 500 and "segments journal line 5 invalid" in r.json()["detail"]
    assert client.get("/health").status_code == 200
    cli = runner.invoke(cli_app, ["verify", "--path", str(p)])
    assert cli.exit_code == 1 and cli.stdout.startswith("TAMPERED — segment 3: segments journal line 5 invalid")


def test_an_incomplete_intent_beside_its_renamed_file_is_a_break(tmp_path):
    """The reviewer's shape: the renamed file exists, as after a kill at rotate.after_rename."""
    p = tmp_path / "ledger" / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 3)
    rotate(s)
    s.append("a", {})
    js = store_mod.parse_journal(journal_path_for(p).read_bytes())
    last = js.closed[-1]
    for missing in ("file", "rotation_event", "head_hash"):
        intent = {"op": "rotate-intent", "format": JOURNAL_FORMAT, "n": 2, "file": "events-2.jsonl",
                  "start_index": last["end_index"] + 1, "end_index": last["end_index"] + 2,
                  "genesis_prev_hash": last["head_hash"], "head_hash": "e" * 64, "anchor": {},
                  "rotation_event": {"hash": "f" * 64}, "at": "now"}
        intent.pop(missing)
        jp = journal_path_for(p)
        good = jp.read_bytes()
        _append_journal(p, intent)
        (p.parent / "events-2.jsonl").write_bytes(p.read_bytes())
        v = LedgerStore(p).verify()
        assert not v.ok and f"rotate-intent field '{missing}' missing" in v.reason, v
        jp.write_bytes(good)
        (p.parent / "events-2.jsonl").unlink()
    assert LedgerStore(p).verify().ok


# ----------------------------------------------- C2R-7: genesis continuity


def test_rotation_after_every_closed_segment_is_archived_continues_from_the_archived_head(tmp_path):
    data, s, p, hashes = _archived_ledger(tmp_path)
    s.append("after", {})
    rot = rotate(s, "after full archival")
    assert rot.rotation_event.payload["genesis_prev_hash"] == hashes[7]  # not the genesis hash
    s.append("after-2", {})
    assert _apply(s, data)["archived_segments"] == [3]
    for n in (1, 2, 3):
        out = verify_segment_file(data / "ledger-archive" / f"events-{n}.jsonl", KEY_PUB)
        assert out["ok"] and out["signature_checked"], (n, out)
    v = LedgerStore(p).verify()
    assert v.ok and v.archived_segments == 3 and v.length == 11 + 1 + 1 + 1 + 1 + 1


@pytest.mark.parametrize("n,expected", [
    (1, (1, 0, "segments journal line 1 invalid: intent n=1 genesis_prev_hash is not the genesis hash")),
    (2, (2, 4, "segments journal line 3 invalid: intent n=2 genesis_prev_hash does not continue the "
               "head of segment 1")),
])
def test_a_journal_intent_that_does_not_start_from_the_previous_head_is_invalid(tmp_path, n, expected):
    s, p, hashes = three_segments(tmp_path)
    _rewrite_journal(p, lambda rec: rec.update(genesis_prev_hash="f" * 64)
                     if rec["op"] == "rotate-intent" and rec["n"] == n else None)
    v = LedgerStore(p).verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == expected[:2], v
    assert v.reason == f"segment {expected[0]}: {expected[2]}"


# --------------------------------- C2R-3: every pinned journal field, alone


@pytest.mark.parametrize("field", ["start_index", "end_index", "genesis_prev_hash", "file", "anchor",
                                   "head_hash"])
def test_an_edit_of_each_journal_field_of_an_archived_segment_is_detected(tmp_path, field):
    """Segments 1 and 2 are archived and their retention event is in the live
    chain, so neither the files nor a missing event can give an edit away:
    only the rotation event that opens the open segment pins entry 2. Where
    the parser would reject a lone edit, the neighbouring record is edited to
    match, so the pin is the only guard left."""
    data, s, p, hashes = _archived_ledger(tmp_path)
    assert LedgerStore(p).verify().ok

    def edit(rec):
        if rec["op"] == "rotate-intent" and rec["n"] == 2:
            rec.update({
                "start_index": {"start_index": 5}, "end_index": {"end_index": 6},
                "genesis_prev_hash": {"genesis_prev_hash": "e" * 64}, "file": {"file": "events-9.jsonl"},
                "head_hash": {"head_hash": "f" * 64}, "anchor": {},
            }[field])
            if field == "anchor":
                rec["anchor"]["anchored_at"] = "2020-01-01T00:00:00+00:00"
        if rec["op"] == "rotate-intent" and rec["n"] == 1:
            if field == "start_index":
                rec["end_index"] = 4
            if field == "genesis_prev_hash":
                rec["head_hash"] = "e" * 64
        if rec["op"] == "archive" and rec["n"] == 2 and field == "file":
            rec["file"] = "events-9.jsonl"

    _rewrite_journal(p, edit)
    v = LedgerStore(p).verify()
    assert not v.ok and v.break_segment == 3, v
    if field == "head_hash":  # the live genesis moves: the link breaks first
        assert v.first_break_index == 8 and v.reason.startswith("segment 3: link break at index 8:")
    else:
        assert v.first_break_index == (7 if field == "end_index" else 8)
        assert v.reason.endswith(f"journal entry for segment 2 disagrees with the hash-chained rotation "
                                 f"event on {field} (journal edited?)")


def test_a_renamed_live_closed_segment_with_its_journal_file_edited_is_detected(tmp_path):
    s, p, hashes = three_segments(tmp_path)
    closed_path_for(p, 1).rename(p.parent / "events-7.jsonl")
    _rewrite_journal(p, lambda rec: rec.update(file="events-7.jsonl")
                     if rec["op"] == "rotate-intent" and rec["n"] == 1 else None)
    v = LedgerStore(p).verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == (2, 4)
    assert "disagrees with the hash-chained rotation event on file" in v.reason


@pytest.mark.parametrize("event_type,segment_closed", [("action.fake", 1), ("ledger.segment.rotated", 2)])
def test_a_segment_boundary_at_an_event_that_is_not_its_rotation_event_is_detected(tmp_path, event_type,
                                                                                 segment_closed):
    """CLM-12: a journal that cuts the chain at an ordinary event whose payload
    copies every pinned field (any API client can post such a payload) is
    caught only by the event type / segment number check."""
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    first = [e.hash for e in fill(s, 4)]
    anchor = {"anchored_at": "2026-09-13T00:00:00+00:00", "chain_length": 4, "head_hash": first[3],
              "segment": 1}
    fake = s.append(event_type, {"segment_closed": segment_closed, "file": "events-1.jsonl",
                                 "start_index": 0, "end_index": 3, "head_hash": first[3],
                                 "genesis_prev_hash": GENESIS_HASH, "anchor": anchor})
    fill(s, 2)
    lines = p.read_text(encoding="utf-8").splitlines()
    closed_path_for(p, 1).write_text("\n".join(lines[:4]) + "\n", encoding="utf-8")
    p.write_text("\n".join(lines[4:]) + "\n", encoding="utf-8")
    _append_journal(p, {"op": "rotate-intent", "format": JOURNAL_FORMAT, "n": 1, "file": "events-1.jsonl",
                        "start_index": 0, "end_index": 3, "genesis_prev_hash": GENESIS_HASH,
                        "head_hash": first[3], "anchor": anchor, "rotation_event": fake.model_dump(),
                        "at": "2026-09-13T00:00:00+00:00"})
    _append_journal(p, {"op": "rotate-commit", "n": 1, "rotation_event_hash": fake.hash,
                        "closed_at": "2026-09-13T00:00:00+00:00"})
    v = LedgerStore(p).verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == (2, 4), v
    assert v.reason == "segment 2: first event is not the rotation event closing segment 1"


# ------------------------- C2R-2 / CLM-1 / CLM-3: the closed-segment head pin


@pytest.mark.parametrize("rewrite", ["last-event-rehashed", "whole-segment-relinked"])
def test_a_closed_segment_rewritten_inside_itself_breaks_at_its_head(tmp_path, rewrite):
    s, p, hashes = three_segments(tmp_path)
    seg1 = closed_path_for(p, 1)
    if rewrite == "last-event-rehashed":
        edit_line(seg1, 3, lambda rec: rec["payload"].update(x=1), rehash=True)
    else:  # same count, every link inside the file intact; only the head moved
        _rewrite_from(seg1, 0, lambda rec: rec["payload"].update(x=1))
    v = LedgerStore(p).verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == (1, 3), v
    assert "does not match the journal's head_hash" in v.reason
    r = runner.invoke(cli_app, ["verify", "--path", str(seg1)])
    assert r.exit_code == 1, r.output
    assert r.stdout.startswith("TAMPERED — segment 1: head ") and "does not match the journal's head_hash" in r.stdout


def test_an_archived_segment_rewritten_inside_itself_fails_its_sidecar_head(tmp_path):
    """CLM-2: count, links, the claimed genesis and the (unsigned) sha256 all
    agree after the rewrite; the head no longer equals the sidecar's head_hash,
    which the signed rotation anchor pins."""
    data, s, p, hashes = _archived_ledger(tmp_path)
    one = data / "ledger-archive" / "events-1.jsonl"
    _rewrite_from(one, 1, lambda rec: rec["payload"].update(n=99))
    side_path = sidecar_path_for(one)
    side = json.loads(side_path.read_text(encoding="utf-8"))
    side["sha256"] = hashlib.sha256(one.read_bytes()).hexdigest()
    side_path.write_text(json.dumps(side), encoding="utf-8")
    for key in (None, KEY_PUB):
        out = verify_segment_file(one, key)
        assert not out["ok"] and "does not match the sidecar head_hash" in out["reason"], (key, out)
    pub = tmp_path / "pub.pem"
    pub.write_text(KEY_PUB, encoding="ascii")
    r = runner.invoke(cli_app, ["verify", "--path", str(one), "--pubkey", str(pub)])
    assert r.exit_code == 1 and "does not match the sidecar head_hash" in r.stdout


def test_a_sidecar_copied_beside_another_file_name_fails(tmp_path):
    data, s, p, hashes = _archived_ledger(tmp_path)
    arch = data / "ledger-archive"
    twin = arch / "copy.jsonl"
    shutil.copyfile(arch / "events-2.jsonl", twin)
    shutil.copyfile(sidecar_path_for(arch / "events-2.jsonl"), sidecar_path_for(twin))
    out = verify_segment_file(twin, KEY_PUB)
    assert not out["ok"] and out["reason"] == "segment 2: sidecar describes 'events-2.jsonl', not 'copy.jsonl'"


# ------------------------------------- C2R-8: guards no test used to kill

_VALID_INTENT_3 = dict(_RECORDS["rotate-intent"])


def _intent_3(hashes: list[str], **changes) -> dict:
    return {**_VALID_INTENT_3, "genesis_prev_hash": hashes[7], "head_hash": hashes[10], **changes}


_STATE_RULES = {
    "intent-n-skips": (lambda h: [_intent_3(h, n=4)], 5, "intent n=4 but the next segment is 3"),
    "intent-start-gap": (lambda h: [_intent_3(h, start_index=9)], 5,
                         "intent indices do not continue the committed segments"),
    "intent-ends-before-it-starts": (lambda h: [_intent_3(h, end_index=7)], 5,
                                     "intent indices do not continue the committed segments"),
    "second-intent-while-pending": (lambda h: [_intent_3(h), _intent_3(h)], 6,
                                    "second intent while one is pending"),
    "commit-names-another-rotation-event": (
        lambda h: [_intent_3(h), {**_RECORDS["rotate-commit"], "rotation_event_hash": "9" * 64}], 6,
        "commit names a different rotation event"),
    "commit-without-intent": (lambda h: [_RECORDS["rotate-commit"]], 5,
                              "rotate-commit for n=3 with no matching intent"),
    "archive-while-pending": (lambda h: [_intent_3(h), _RECORDS["archive"]], 6,
                              "archive while a rotation is pending"),
    "archive-not-the-oldest": (lambda h: [{**_RECORDS["archive"], "n": 2, "file": "events-2.jsonl"}], 5,
                               "archive n=2 is not the oldest live closed segment"),
    "archive-names-another-file": (lambda h: [{**_RECORDS["archive"], "file": "events-2.jsonl"}], 5,
                                   "archive n=1 is not the oldest live closed segment"),
}


@pytest.mark.parametrize("rule", sorted(_STATE_RULES))
def test_each_journal_state_machine_rule_is_a_break(tmp_path, rule):
    s, p, hashes = three_segments(tmp_path)
    build, line, message = _STATE_RULES[rule]
    for rec in build(hashes):
        _append_journal(p, rec)
    v = LedgerStore(p).verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == (3, 8), v
    assert v.reason == f"segment 3: segments journal line {line} invalid: {message}"


@pytest.mark.parametrize("variant", ["operator-and-reason", "timestamp-then-relinked"])
def test_a_rotation_event_rewritten_at_the_start_of_the_open_segment_breaks(tmp_path, variant):
    """C2R-8 (2) / CLM-12: same payload fields the journal pins, re-hashed (and
    the segment re-linked): only "starts with the recorded rotation event" sees it."""
    if variant == "operator-and-reason":
        p = tmp_path / "events.jsonl"
        s = LedgerStore(p)
        fill(s, 3)
        rotate(s)
        _rewrite_from(p, 0, lambda rec: rec["payload"].update(operator="mallory", reason="forged"))
        where = (2, 3)
    else:
        s, p, hashes = three_segments(tmp_path)
        _rewrite_from(p, 0, lambda rec: rec.update(ts="2020-01-01T00:00:00+00:00"))
        where = (3, 8)
    v = LedgerStore(p).verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == where, v
    assert v.reason.startswith(f"segment {where[0]}: does not start with the recorded rotation event ")


@pytest.mark.parametrize("damage", ["renamed-segment-truncated", "renamed-segment-head-rehashed",
                                    "open-segment-first-event-replaced"])
def test_reconcile_refuses_a_tampered_pending_rotation_and_commits_nothing(tmp_path, damage):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 4)
    _pending_rotation(s, installed=damage.startswith("open"))
    seg1 = closed_path_for(p, 1)
    if damage == "renamed-segment-truncated":
        lines = seg1.read_text(encoding="utf-8").splitlines()
        seg1.write_text("\n".join(lines[:3]) + "\n", encoding="utf-8")
        why = "pending rotation 1: events-1.jsonl does not match the intent"
    elif damage == "renamed-segment-head-rehashed":
        edit_line(seg1, 3, lambda rec: rec["payload"].update(x=1), rehash=True)
        why = "pending rotation 1: events-1.jsonl does not match the intent"
    else:
        _rewrite_from(p, 0, lambda rec: rec["payload"].update(reason="forged"))
        why = "pending rotation 1: the open segment does not start with the intended rotation event"
    journal_before = journal_path_for(p).read_bytes()
    fresh = LedgerStore(p)
    assert fresh.needs_reconcile()
    with pytest.raises(LedgerCorrupt, match=why):
        fresh.reconcile()
    assert journal_path_for(p).read_bytes() == journal_before
    assert [r["op"] for r in journal_records(p)] == ["rotate-intent"]


def test_a_closed_segment_archived_between_validation_and_its_read_is_retried(tmp_path, monkeypatch):
    """C2R-8 (4): the snapshot validated a layout in which segment 1 was live,
    then archival moved it before it was read. A changed journal means "take
    another snapshot", never "file missing"."""
    s, p, hashes = three_segments(tmp_path / "ledger")
    seg1 = closed_path_for(p, 1)
    real = store_mod.read_shared
    moved: list = []

    def archive_just_before_the_read(path):
        if Path(path) == seg1 and not moved:
            moved.append(archive_oldest_for_test(LedgerStore(p), tmp_path / "archive"))
        return real(path)

    reader = LedgerStore(p)
    monkeypatch.setattr(store_mod, "read_shared", archive_just_before_the_read)
    snap = reader.snapshot()
    assert moved and snap.attempts >= 2
    v = snap.verify()
    assert v.ok and v.archived_segments == 1 and v.length == 11, v


def test_an_anchor_in_a_missing_live_segment_fails_as_missing(tmp_path):
    s, p, hashes = three_segments(tmp_path / "ledger")
    anchors = tmp_path / "anchors.jsonl"
    anchors.write_text(pre_c2_anchor_line(6, hashes[5]), encoding="utf-8")
    assert verify_anchors(LedgerStore(p), anchors, public_key_pem=KEY_PUB).ok
    closed_path_for(p, 2).unlink()
    r = verify_anchors(LedgerStore(p), anchors, public_key_pem=KEY_PUB)
    assert not r.ok and r.first_failure == (
        "anchor 0: position 6 (global index 5) is missing from the live chain (segment file absent)")


def test_cli_verify_uses_the_journal_even_with_a_stray_sidecar_beside_the_open_segment(tmp_path):
    s, p, hashes = three_segments(tmp_path)
    sidecar_path_for(p).write_text('{"format": "not a sidecar"}\n', encoding="utf-8")
    r = runner.invoke(cli_app, ["verify", "--path", str(p)])
    assert r.exit_code == 0, r.output
    assert r.stdout.splitlines() == ["OK — chain intact over 11 events",
                                     "(3 segments, 0 archived; 11 events hash-verified)"]


def _claim_archived_prefix(bundle: Path, drop: int, archived_segments: int) -> None:
    lines = (bundle / "events.jsonl").read_text(encoding="utf-8").splitlines()
    kept = [json.loads(x) for x in lines[drop:]]
    (bundle / "events.jsonl").write_text("\n".join(lines[drop:]) + "\n", encoding="utf-8")
    sm = json.loads((bundle / "summary.json").read_text(encoding="utf-8"))
    cp = json.loads((bundle / "chain_proof.json").read_text(encoding="utf-8"))
    for doc in (sm, cp):
        doc["verification"].update(segments=1, verified_events=doc["verification"]["length"] - drop,
                                   archived_segments=archived_segments, break_segment=None)
        doc["first_index"] = drop
    sm["indices"] = list(range(drop, drop + len(kept)))
    sm["event_count"] = len(kept)
    sm["event_types"], sm["agents"] = {}, {}
    for rec in kept:
        sm["event_types"][rec["event_type"]] = sm["event_types"].get(rec["event_type"], 0) + 1
        key = rec["agent_id"] or "<none>"
        sm["agents"][key] = sm["agents"].get(key, 0) + 1
    sm["first_ts"] = kept[0]["ts"]
    cp["first_prev_hash"] = kept[0]["prev_hash"]
    cp["spine"] = cp["spine"][drop:]
    (bundle / "summary.json").write_text(json.dumps(sm, indent=2), encoding="utf-8")
    (bundle / "chain_proof.json").write_text(json.dumps(cp, indent=2), encoding="utf-8")


def test_a_bundle_exporting_an_index_below_its_claimed_archived_prefix_fails(tmp_path):
    s, p, hashes = three_segments(tmp_path / "ledger")
    bundle = Path(s.export(tmp_path / "exports").bundle_dir)
    for name in ("summary.json", "chain_proof.json"):
        doc = json.loads((bundle / name).read_text(encoding="utf-8"))
        doc["verification"].update(verified_events=3, archived_segments=2)
        (bundle / name).write_text(json.dumps(doc, indent=2), encoding="utf-8")
    res = verify_bundle(bundle)
    assert not res.ok and res.first_failing_index == 0
    assert "index 0 is exported but the verification says indices 0..7 are archived" in res.reason


def test_a_claimed_archived_prefix_must_end_at_a_rotation_event_that_links_to_its_head(tmp_path):
    """CLM-12: the first live event carries the right type, range and segment
    number, but its recorded head is not the hash it links to."""
    s = LedgerStore(tmp_path / "ledger" / "events.jsonl")
    fill(s, 8)
    s.append("ledger.segment.rotated", {"segment_closed": 1, "end_index": 7, "head_hash": "f" * 64})
    fill(s, 2)
    bundle = Path(s.export(tmp_path / "exports").bundle_dir)
    assert verify_bundle(bundle).ok
    _claim_archived_prefix(bundle, 8, 1)
    res = verify_bundle(bundle)
    assert not res.ok and "index 8 should be the rotation event closing archived segment 1" in res.reason


# ------------------------------------------- C2R-4: partial retention runs


@pytest.mark.parametrize("interference", ["hold-placed", "segment-2-damaged"])
def test_apply_refused_after_archiving_a_segment_still_ledgers_it(tmp_path, monkeypatch, interference):
    data = tmp_path / "data"
    s, p, hashes = three_segments(data / "ledger")
    arch = data / "ledger-archive"
    real = LedgerStore._move_one

    def move_then_interfere(self, src, dst, digest):
        out = real(self, src, dst, digest)
        if src.name == "events-1.jsonl":
            if interference == "hold-placed":
                LedgerStore(p).place_hold(by="counsel", reason="litigation")
            else:
                edit_line(closed_path_for(p, 2), 1, lambda rec: rec["payload"].update(n=42))
        return out

    monkeypatch.setattr(LedgerStore, "_move_one", move_then_interfere)
    written: list = []
    real_sidecar = LedgerStore._write_sidecar
    monkeypatch.setattr(LedgerStore, "_write_sidecar",
                        lambda self, sidecar, side: written.append(sidecar.name) or real_sidecar(self, sidecar, side))
    expected = LegalHoldActive if interference == "hold-placed" else LedgerCorrupt
    with pytest.raises(expected):
        _apply(s, data)
    monkeypatch.setattr(LedgerStore, "_move_one", real)
    monkeypatch.setattr(LedgerStore, "_write_sidecar", real_sidecar)
    assert written == ["events-1.jsonl.segment.json"]  # nothing is written for segment 2 under the hold
    assert [r["n"] for r in journal_records(p) if r["op"] == "archive"] == [1]
    applied = [e for e in LedgerStore(p).events() if e.event_type == "ledger.retention.applied"]
    assert len(applied) == 1, applied
    assert applied[0].payload["archived_segments"] == [1]
    assert applied[0].payload["error"].startswith(expected.__name__ + ": ")
    assert not sidecar_path_for(arch / "events-2.jsonl").exists()
    if interference == "hold-placed":
        assert LedgerStore(p).verify().ok
        LedgerStore(p).release_hold(by="counsel")
        assert _apply(LedgerStore(p), data, operator="another-operator")["archived_segments"] == [2]
    else:
        v = LedgerStore(p).verify()
        assert not v.ok and v.break_segment == 2


def test_a_hold_placed_after_the_sidecar_is_written_leaves_no_sidecar_behind(tmp_path, monkeypatch):
    data = tmp_path / "data"
    s, p, hashes = three_segments(data / "ledger")
    real = LedgerStore._write_sidecar
    placed: list = []

    def sidecar_then_hold(self, sidecar, side):
        created = real(self, sidecar, side)
        if not placed:
            t = threading.Thread(target=lambda: placed.append(
                LedgerStore(p).place_hold(by="counsel", reason="late")))
            t.start()
            t.join(30)
        return created

    monkeypatch.setattr(LedgerStore, "_write_sidecar", sidecar_then_hold)
    with pytest.raises(LegalHoldActive):
        _apply(s, data)
    assert placed and not sidecar_path_for(data / "ledger-archive" / "events-1.jsonl").exists()
    assert [r["op"] for r in journal_records(p)].count("archive") == 0
    assert "ledger.retention.applied" not in [e.event_type for e in LedgerStore(p).events()]


# ------------------------------------ C2R-10: pending move / pending rotation


def test_cli_verify_of_a_pending_move_checks_its_journal_entry_and_digest(tmp_path, monkeypatch):
    data = tmp_path / "data"
    s, p, hashes = three_segments(data / "ledger")
    real = LedgerStore._move_one
    monkeypatch.setattr(LedgerStore, "_move_one", lambda self, src, dst, digest: "pending")
    r = _apply(s, data)
    monkeypatch.setattr(LedgerStore, "_move_one", real)
    assert [m["n"] for m in r["pending_moves"]] == [1, 2]
    seg2 = closed_path_for(p, 2)
    out = runner.invoke(cli_app, ["verify", "--path", str(seg2)])
    assert out.exit_code == 0, out.output
    assert out.stdout.splitlines()[0] == "OK — segment 2 of events.jsonl intact over 4 events (global 4..7)"
    assert "a pending move" in out.stdout
    seg2.write_bytes(seg2.read_bytes() + b"\n")  # still chains; not the bytes archival hashed
    out = runner.invoke(cli_app, ["verify", "--path", str(seg2)])
    assert out.exit_code == 1
    assert out.stdout.startswith("TAMPERED — segment 2: file bytes differ from the sha256 journaled at archival")
    v = LedgerStore(p).verify()
    assert not v.ok and (v.break_segment, v.first_break_index) == (2, 4)


def test_cli_verify_of_a_pending_rotation_s_renamed_segment_uses_its_intent(tmp_path):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 4)
    rotate(s)
    fill(s, 2)
    _pending_rotation(s, installed=False)  # segment 2 renamed, not yet committed
    out = runner.invoke(cli_app, ["verify", "--path", str(closed_path_for(p, 2))])
    assert out.exit_code == 0, out.output
    assert out.stdout.splitlines() == [
        "OK — segment 2 of events.jsonl intact over 3 events (global 4..6)",
        "(rotation 2 is pending: the service or the next write commits it)",
    ]


# ------------------------------------------------ C2R-11: retention check


class _Registry:
    def list_agents(self, *a, **k):
        return []


def test_retention_check_never_invents_ledger_state_it_could_not_read(tmp_path, monkeypatch):
    data = tmp_path / "data"
    s, p, hashes = three_segments(data / "ledger")
    s.place_hold(by="counsel", reason="litigation")
    monkeypatch.setenv("FIELD_LEDGER_RETENTION_DAYS", "2555")

    def unreadable(self):
        raise PermissionError(13, "journal held (simulated winerror 32)")

    monkeypatch.setattr(LedgerStore, "retention_state", unreadable)
    body = TestClient(create_app(store=s, registry=_Registry())).get("/retention/check").json()
    assert body["ok"] is False and body["status"] == "unavailable", body
    for key in ("legal_hold", "segments", "archived_segments", "pending_moves", "earliest_live_index",
                "earliest_live_ts"):
        assert body[key] is None, key
    assert "ledger state unreadable: PermissionError" in body["detail"]


# ------------------------------------------------------ C2PD-2 / C2PD-3: /health


def test_health_does_not_recount_while_this_store_s_own_append_is_in_flight(tmp_path, monkeypatch):
    s, p, hashes = three_segments(tmp_path)
    assert s.health_info()["event_count"] == 11
    calls: list = []
    real_take = LedgerStore._take_snapshot
    monkeypatch.setattr(LedgerStore, "_take_snapshot",  # this store's snapshots only
                        lambda self, *a, **k: (self is s and calls.append(k)) or real_take(self, *a, **k))
    seen: list = []
    real_fstat = os.fstat
    armed = [True]

    def fstat_then_health(fd):
        st = real_fstat(fd)
        if armed[0] and threading.current_thread() is threading.main_thread():
            armed[0] = False  # the append is written and fsynced, not yet in the cache
            seen.append((s._disk_key() != s._health[2], s.health_info()["event_count"]))
        return st

    monkeypatch.setattr(os, "fstat", fstat_then_health)
    s.append("mine", {})
    monkeypatch.setattr(os, "fstat", real_fstat)
    assert seen == [(True, 11)] and calls == []  # the disk had moved; no out-of-band recount
    assert s.health_info()["event_count"] == 12 and calls == []
    LedgerStore(p).append("another-writer", {})  # a real out-of-band change is still recounted
    assert s.health_info()["event_count"] == 13 and len(calls) == 1


def _replace_line(path: Path, k: int, how: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if how == "non-json":
        lines[k] = "this record was overwritten\n"
    else:
        lines[k] = json.dumps({x: v for x, v in json.loads(lines[k]).items() if x != "hash"}) + "\n"
    path.write_text("".join(lines), encoding="utf-8")


@pytest.mark.parametrize("how", ["non-json", "required-key-deleted"])
@pytest.mark.parametrize("where", ["single-file", "closed-segment", "open-segment"])
@pytest.mark.parametrize("opened", ["before-the-tamper", "after-the-tamper"])
def test_an_unparseable_record_is_a_break_on_verify_never_a_500(tmp_path, how, where, opened):
    """C4R-9: GET /verify on a record that does not parse answers 200 ok=false
    with its GLOBAL first_break_index and a reason — single-file and segmented.
    A running store's appends refuse (500 LedgerCorrupt) instead of chaining
    past it. LIMIT (pinned, as before C2 — test_torn_last_line_raises_as_today):
    a store cannot be OPENED on an open segment holding such a line, so a
    ledger process restarted on it does not start at all."""
    if where == "single-file":
        p = tmp_path / "ledger" / "events.jsonl"
        s = LedgerStore(p)
        fill(s, 5, "a")
        target, k, index, prefix = p, 2, 2, ""
    else:
        s, p, hashes = three_segments(tmp_path / "ledger")
        if where == "closed-segment":
            target, k, index, prefix = closed_path_for(p, 2), 1, 5, "segment 2: "
        else:
            target, k, index, prefix = p, 1, 9, "segment 3: "
    if opened == "before-the-tamper":
        client = TestClient(create_app(store=s), raise_server_exceptions=False)
        _replace_line(target, k, how)
    else:
        _replace_line(target, k, how)
        if target == p:
            with pytest.raises(ValueError):
                LedgerStore(p)
            return
        client = TestClient(create_app(store=LedgerStore(p)), raise_server_exceptions=False)
    r = client.get("/verify")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False and body["first_break_index"] == index, body
    kind = "JSONDecodeError" if how == "non-json" else "ValidationError"
    assert body["reason"].startswith(f"{prefix}unparseable record at index {index}: {kind}: "), body
    if target == p:  # the writer's own segment: nothing is chained past it
        before = p.read_bytes()
        r = client.post("/events", json={"event_type": "after", "payload": {}})
        assert r.status_code == 500 and "unreadable" in r.json()["detail"], r.text
        assert p.read_bytes() == before


def test_an_earlier_real_break_keeps_its_index_before_an_unparseable_record(tmp_path):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 6, "a")
    edit_line(p, 1, lambda rec: rec["payload"].update(tampered=True))
    _replace_line(p, 4, "non-json")
    v = s.verify()  # the running store (a fresh one cannot open on this open segment)
    assert (v.ok, v.first_break_index) == (False, 1) and v.reason.startswith("hash mismatch at index 1:"), v


def test_health_does_not_recount_during_the_append_that_creates_a_new_ledger(tmp_path, monkeypatch):
    """REG (C2PD-2 edge): the first append to a brand-new ledger creates the
    open segment, so there is no prior disk key to grow. /health during that
    append — the empty file just created, and the line written and fsynced but
    not yet cached — must still answer from the cache, with no recount."""
    p = tmp_path / "fresh" / "events.jsonl"
    s = LedgerStore(p)
    assert not p.exists() and s.health_info()["event_count"] == 0
    calls: list = []
    real_take = LedgerStore._take_snapshot
    monkeypatch.setattr(LedgerStore, "_take_snapshot",
                        lambda self, *a, **k: (self is s and calls.append(k)) or real_take(self, *a, **k))
    seen: list = []
    real_open = Path.open

    def open_then_health(path_self, *a, **k):
        fh = real_open(path_self, *a, **k)
        if path_self == p and not seen:
            seen.append(("created", p.stat().st_size, s.health_info()["event_count"]))
        return fh

    real_fstat = os.fstat

    def fstat_then_health(fd):
        st = real_fstat(fd)
        if len(seen) == 1 and threading.current_thread() is threading.main_thread():
            seen.append(("written", p.stat().st_size, s.health_info()["event_count"]))
        return st

    monkeypatch.setattr(Path, "open", open_then_health)
    monkeypatch.setattr(os, "fstat", fstat_then_health)
    s.append("first", {})
    monkeypatch.setattr(os, "fstat", real_fstat)
    monkeypatch.setattr(Path, "open", real_open)
    assert [(what, size > 0, count) for what, size, count in seen] == [
        ("created", False, 0), ("written", True, 0)], seen
    assert calls == []  # the disk moved twice; neither was taken for another process's write
    assert s.health_info()["event_count"] == 1 and calls == []
    LedgerStore(p).append("another-writer", {})  # a real out-of-band change is still recounted
    assert s.health_info()["event_count"] == 2 and len(calls) == 1


def test_health_out_of_band_recount_takes_no_lock_no_gate_and_no_pydantic(tmp_path, monkeypatch):
    s, p, hashes = three_segments(tmp_path / "ledger")
    client = TestClient(create_app(store=s))
    assert client.get("/health").json()["event_count"] == 11
    LedgerStore(p).append("elsewhere", {})  # the cache key no longer matches the disk
    calls: list = []
    parsed: list = []
    real_take = LedgerStore._take_snapshot
    monkeypatch.setattr(LedgerStore, "_take_snapshot",
                        lambda self, *a, **k: calls.append(k) or real_take(self, *a, **k))
    real_parse = store_mod._parse_events
    monkeypatch.setattr(store_mod, "_parse_events", lambda data: parsed.append(len(data)) or real_parse(data))
    held = threading.Event()
    release = threading.Event()

    def hold_everything():
        with s._writer():
            with s._gate():
                held.set()
                release.wait(30)

    t = threading.Thread(target=hold_everything)
    t.start()
    try:
        assert held.wait(10)
        t0 = time.monotonic()
        h = client.get("/health").json()
        assert time.monotonic() - t0 < 2.0
        assert h["event_count"] == 12
        assert calls == [{"parse": False, "open_only": True}] and parsed == []
    finally:
        release.set()
        t.join(10)


# --------------------------------------------------- C2PD-4: the read gate


@pytest.mark.parametrize("setting,width", [(None, 1), ("2", 2), ("0", 0)])
def test_heavy_read_gate_width(tmp_path, monkeypatch, setting, width):
    if setting is not None:
        monkeypatch.setenv("FIELD_LEDGER_READ_CONCURRENCY", setting)
    s, p, hashes = three_segments(tmp_path)
    assert s.read_concurrency == width
    assert create_app(store=s).state.lanes["read"]._max_workers == (width or 32)
    release = threading.Event()
    holders = []
    for _ in range(width or 3):  # take every slot (3 of "unlimited")
        entered = threading.Event()

        def hold(entered=entered):
            with s._gate():
                entered.set()
                release.wait(30)

        t = threading.Thread(target=hold)
        t.start()
        holders.append(t)
        assert entered.wait(10)
    done = threading.Event()
    reader = threading.Thread(target=lambda: (s.snapshot(), done.set()))
    reader.start()
    try:
        if width:
            assert not done.wait(0.5), "a full-chain read ran while every gate slot was held"
            release.set()
        assert done.wait(10)
    finally:
        release.set()
        reader.join(10)
        for t in holders:
            t.join(10)


# ------------------------------------------ C2PD-6 / C2PD-7: served startup


def test_served_startup_never_writes_a_ledger_that_needs_no_reconcile(tmp_path, monkeypatch):
    data = tmp_path / "data"
    p = data / "ledger" / "events.jsonl"
    _hand_chained(p, 3)  # the pre-C2 upgrade shape: no lock file, no journal
    before = listing(p.parent)
    assert list(before) == ["events.jsonl"]
    client = TestClient(create_app())
    assert client.get("/health").json()["event_count"] == 3
    assert listing(p.parent) == before
    reconciles: list = []
    monkeypatch.setattr(LedgerStore, "reconcile", lambda self: reconciles.append(1) or "clean")
    TestClient(create_app()).get("/health")
    assert reconciles == [] and listing(p.parent) == before


def test_served_startup_with_a_rotation_it_cannot_reconcile_still_serves(tmp_path):
    data = tmp_path / "data"
    p = data / "ledger" / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 4)
    _pending_rotation(s, installed=False)
    seg1 = closed_path_for(p, 1)
    lines = seg1.read_text(encoding="utf-8").splitlines()
    seg1.write_text("\n".join(lines[:3]) + "\n", encoding="utf-8")  # no longer what the intent recorded
    assert LedgerStore(p).needs_reconcile()
    client = TestClient(create_app(), raise_server_exceptions=False)  # returns: no crash loop
    assert client.get("/health").status_code == 200
    v = client.get("/verify").json()
    assert v["ok"] is False and v["break_segment"] == 1
    r = client.post("/events", json={"event_type": "x"})
    assert r.status_code == 500 and "does not match the intent" in r.json()["detail"]


# --------------------------------------- C2PD-8: a refused rename is cheap


@pytest.mark.parametrize("refusal", ["held-open", "name-taken"])
def test_a_refused_rename_does_not_re_parse_the_open_segment(tmp_path, monkeypatch, refusal):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    hashes = [e.hash for e in fill(s, 5)]
    recovers: list = []
    real = LedgerStore._recover_locked
    monkeypatch.setattr(LedgerStore, "_recover_locked", lambda self: recovers.append(1) or real(self))

    def refused(src, dst):
        if refusal == "held-open":
            raise PermissionError(13, "held open (simulated winerror 32)")
        raise RotationRefused(f"{dst.name} already exists; refusing to overwrite it")

    s._rename_with_retry = refused
    with pytest.raises(LedgerBusy if refusal == "held-open" else RotationRefused):
        rotate(s)
    del s._rename_with_retry
    assert recovers == []
    assert [r["op"] for r in journal_records(p)] == ["rotate-intent", "rotate-abort"]
    assert s._c.disk_key == s._disk_key() and s._health[2] == s._disk_key() and not s._c.pending
    assert s.health_info()["event_count"] == 5
    hashes.append(s.append("after", {}).hash)
    assert recovers == []  # the refreshed cache was trusted, and it was right
    hashes.append(rotate(s).rotation_event.hash)
    v = LedgerStore(p).verify()
    assert v.ok and v.length == 7 and v.segments == 2
    assert [e.hash for e in LedgerStore(p).events()] == hashes


# -------------------------------------------------- C4R-5: unknown key OID


def _der(tag: int, body: bytes) -> bytes:
    return bytes([tag]) + (bytes([len(body)]) if len(body) < 128 else bytes([0x81, len(body)])) + body


def test_rotate_with_a_key_of_an_unknown_algorithm_is_503(tmp_path, monkeypatch):
    pkcs8 = _der(0x30, _der(0x02, b"\x00") + _der(0x30, _der(0x06, bytes([0x2A, 0x03, 0x04, 0x05])))
                 + _der(0x04, _der(0x04, os.urandom(32))))
    key = tmp_path / "keys" / "unknown-oid.pem"
    key.parent.mkdir()
    key.write_text("-----BEGIN PRIVATE KEY-----\n" + base64.encodebytes(pkcs8).decode()
                   + "-----END PRIVATE KEY-----\n", encoding="ascii")
    with pytest.raises(NoAnchorKey, match=r"^anchor key unusable \(--key\): not a PEM private key"):
        load_anchor_key(key)
    monkeypatch.setenv("FIELD_LEDGER_ANCHOR_KEY", str(key))
    p = tmp_path / "ledger" / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 3)
    before = listing(p.parent)
    client = TestClient(create_app(store=s), raise_server_exceptions=False)
    r = client.post("/rotate", json={"operator": "ops", "reason": "quarterly"})
    assert r.status_code == 503 and r.json()["detail"].startswith("anchor key unusable"), r.text
    assert listing(p.parent) == before


# ------------------------------------- C2PD-1 / C2R-12: real uvicorn serving


def test_health_and_appends_do_not_wait_behind_queued_heavy_reads(tmp_path):
    """C2PD-1: 60 /verify queued on the read gate used to hold 40 of them in
    Starlette's shared 40-thread pool, so /health and appends waited for a
    thread. The gate is HELD by the test here, so every queued read waits
    without using CPU: what is measured is thread starvation alone, not the
    GIL contention a running parse adds (see README LIMITS)."""
    s, p, hashes = three_segments(tmp_path / "ledger")
    app = create_app(store=s)
    server, thread, port = _serve(app, graceful=1.0)
    held = threading.Event()
    release = threading.Event()

    def hold_the_gate():
        with s._gate():
            held.set()
            release.wait(120)

    holder = threading.Thread(target=hold_the_gate)
    holder.start()
    assert held.wait(10)
    reads: list = []
    readers = [threading.Thread(target=lambda: reads.append(_req(port, "GET", "/verify", timeout=120)),
                                daemon=True) for _ in range(60)]
    try:
        for r in readers:
            r.start()
        time.sleep(3.0)  # every reader connected and waiting on the gate
        health = [_req(port, "GET", "/health", timeout=2.0) for _ in range(5)]
        appends = [_req(port, "POST", "/events", body={"event_type": "while-readers-queue"}, timeout=5.0)
                   for _ in range(3)]
        print(f"\n/health {[round(h[0], 3) for h in health]} s; appends {[round(a[0], 3) for a in appends]} s")
        assert all(status == 200 and dt < 2.0 for dt, status, _ in health), health
        assert all(status == 201 and dt < 5.0 for dt, status, _ in appends), appends
    finally:
        release.set()
        holder.join(10)
        for r in readers:
            r.join(60)
        server.should_exit = True
        thread.join(60)
        for lane in app.state.lanes.values():
            lane.shutdown(wait=False, cancel_futures=True)
    # the queued reads were only delayed: each one answered once the gate opened
    assert len(reads) == 60 and all(status == 200 and json.loads(body)["ok"] for _, status, body in reads)


def test_served_concurrency_uvicorn(tmp_path, monkeypatch):
    """Build spec §6: a real server with 4 /verify loops, appends and two
    POST /rotate at once. Every append is kept in order, every /verify is ok
    (or busy, never a break) and never shorter than what was acked before it."""
    keyfile = tmp_path / "keys" / "anchor.pem"
    keyfile.parent.mkdir()
    keyfile.write_text(KEY_PRIV, encoding="ascii")
    monkeypatch.setenv("FIELD_LEDGER_ANCHOR_KEY", str(keyfile))
    p = tmp_path / "ledger" / "events.jsonl"
    base = _hand_chained(p, 2_000)
    server, thread, port = _serve(create_app(store=LedgerStore(p)))
    stop = time.monotonic() + 4.0
    acked: list[str] = []
    bad: list = []
    verified = [0]

    def verifier():
        while time.monotonic() < stop:
            floor = len(base) + len(acked)
            dt, status, data = _req(port, "GET", "/verify", timeout=60)
            if status != 200:
                bad.append(("verify status", status))
                continue
            body = json.loads(data)
            if not body["ok"] and not (body["reason"] or "").startswith("ledger busy"):
                bad.append(("verify break", body["reason"]))
            elif body["ok"] and body["length"] < floor:
                bad.append(("SHORT", body["length"], floor))
            verified[0] += 1

    def appender():
        k = 0
        while time.monotonic() < stop:
            dt, status, data = _req(port, "POST", "/events", body={"event_type": "c", "payload": {"k": k}},
                                    timeout=30)
            if status != 201:
                bad.append(("append", status))
                continue
            acked.append(json.loads(data)["hash"])
            k += 1

    threads = [threading.Thread(target=verifier) for _ in range(4)] + [threading.Thread(target=appender)]
    rotations = []
    try:
        for t in threads:
            t.start()
        for delay in (1.0, 1.5):
            time.sleep(delay)
            dt, status, data = _req(port, "POST", "/rotate", body={"operator": "ops", "reason": "load"},
                                    timeout=60)
            rotations.append((status, dt))
        for t in threads:
            t.join(120)
        _, status, data = _req(port, "GET", "/health", timeout=5)
        health = json.loads(data)
    finally:
        server.should_exit = True
        thread.join(60)
    print(f"\nserved concurrency: {verified[0]} verifies, {len(acked)} appends, rotations {rotations}")
    assert bad == [] and [s for s, _ in rotations] == [200, 200], (bad[:5], rotations)
    assert verified[0] >= 4 and acked
    events = [e.hash for e in LedgerStore(p).events()]
    final = LedgerStore(p).verify()
    assert final.ok and final.segments == 3 and final.length == len(base) + len(acked) + 2
    assert events[: len(base)] == base
    live_appends = [h for h in events[len(base):] if h in set(acked)]
    assert live_appends == acked  # every ack present, in order
    assert health["event_count"] == final.length
