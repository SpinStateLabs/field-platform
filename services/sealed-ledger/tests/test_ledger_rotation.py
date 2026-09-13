"""C2 — ledger retention by rotation: layout, rotate, verify across segments,
anchors, export, /health, the served POST /rotate and the CLI.

Done-when (tasks/todo.md C2, C2 build spec §6.1/§6.2) for the rotation core.
Retention apply, sidecars, legal hold and retention check are separate
(c2-ops); archived-segment READ paths are tested here through
``archive_oldest_for_test``, which writes the journal ``archive`` op and moves
the file in the build spec's order.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from field_core.ledger import GENESIS_HASH, ChainVerification, verify_chain
from field_core.signing import generate_keypair, verify_manifest
from ledger_c2_support import (
    KEY_PRIV,
    KEY_PUB,
    SLOW,
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
from sealed_ledger.anchors import AnchorRecord, signed_view, verify_anchors, write_anchor
from sealed_ledger.api import create_app
from sealed_ledger.bundle import verify_bundle
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import (
    LedgerBusy,
    LedgerCorrupt,
    LedgerStore,
    NoAnchorKey,
    RotationRefused,
    closed_path_for,
    journal_path_for,
)

runner = CliRunner()
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _key_file(tmp_path: Path, pem: str = KEY_PRIV) -> Path:
    keys = tmp_path / "keys"
    keys.mkdir(exist_ok=True)
    f = keys / "anchor.pem"
    f.write_text(pem, encoding="ascii")
    return f


# ------------------------------------------------------------ plan Done-when


def test_rotate_twice_verify_ok_across_three_segments(tmp_path):
    s, p, hashes = three_segments(tmp_path)
    fresh = LedgerStore(p)
    v = fresh.verify()
    assert v.ok and v.length == 11 and v.segments == 3 and v.archived_segments == 0
    assert v.verified_events == 11 and v.break_segment is None
    assert [e.hash for e in fresh.events()] == hashes
    assert fresh.global_length() == 11 and fresh.head_hash == hashes[-1]
    client = TestClient(create_app(store=fresh))
    health = client.get("/health").json()
    assert health["event_count"] == 11 and health["head_hash"] == hashes[-1]
    assert health["earliest_live_index"] == 0
    served = client.get("/verify").json()
    assert served["length"] == 11 and served["segments"] == 3
    assert set(served) == {"ok", "length", "first_break_index", "reason", "segments",
                           "archived_segments", "verified_events", "break_segment"}
    # line k of each file is global event start + k
    assert [json.loads(x)["hash"] for x in p.read_text(encoding="utf-8").splitlines()] == hashes[8:]
    seg1 = closed_path_for(p, 1).read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["hash"] for x in seg1] == hashes[:4]
    rot = fresh.events()[8]
    assert rot.event_type == "ledger.segment.rotated" and rot.prev_hash == hashes[7]
    assert rot.payload["operator"] == "tester" and rot.payload["reason"] == "r2"
    assert rot.payload["segment_closed"] == 2 and rot.payload["start_index"] == 4
    r = runner.invoke(cli_app, ["verify", "--path", str(p)])
    assert r.exit_code == 0, r.output
    assert r.stdout.splitlines() == [
        "OK — chain intact over 11 events",
        "(3 segments, 0 archived; 11 events hash-verified)",
    ]


def test_store_opened_as_e_jsonl_rotates(tmp_path):
    s = LedgerStore(tmp_path / "e.jsonl")
    fill(s, 3)
    res = rotate(s)
    assert res.file == "e-1.jsonl" and res.segment == 1
    assert (res.start_index, res.end_index) == (0, 2)
    assert sorted(x.name for x in tmp_path.iterdir()) == [
        ".e.jsonl.lock", "e-1.jsonl", "e.jsonl", "e.segments.journal",
    ]
    v = LedgerStore(tmp_path / "e.jsonl").verify()
    assert v.ok and v.length == 4 and v.segments == 2


def test_reader_mid_iteration_in_another_thread_then_rotate(tmp_path):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 20)
    started = threading.Event()
    release = threading.Event()
    stop = threading.Event()
    bad: list = []
    lengths: list[int] = []

    def half_consumed_iterator():
        it = s.iter_events()
        for _ in range(10):
            next(it)
        started.set()
        release.wait(30)
        rest = list(it)
        if len(rest) != 10:
            bad.append(f"iterator lost events: {len(rest)}")

    def verifier():
        floor = 20
        while not stop.is_set():
            v = LedgerStore(p).verify()
            if not v.ok:
                bad.append(v.reason)
            elif v.length < floor:
                bad.append(f"ok with {v.length} < {floor}")
            else:
                floor = v.length
                lengths.append(v.length)

    threads = [threading.Thread(target=half_consumed_iterator), threading.Thread(target=verifier)]
    for t in threads:
        t.start()
    assert started.wait(30)
    for _ in range(5):
        rotate(s)  # never 503 here: this code's readers never hold a blocking handle
        s.append("after", {})
    release.set()
    stop.set()
    for t in threads:
        t.join(60)
    assert bad == []
    assert lengths, "the verifier never completed a read"
    assert LedgerStore(p).verify().length == 20 + 5 + 5


def test_second_writer_size_mismatch(tmp_path):
    """Two instances, one file: a stale instance re-reads the true head (and a
    rotation another instance made) before it writes."""
    p = tmp_path / "events.jsonl"
    a = LedgerStore(p)
    b = LedgerStore(p)
    acked = [a.append("a", {}).hash, b.append("b", {}).hash, a.append("a", {}).hash]
    acked.append(rotate(b).rotation_event.hash)
    acked.append(a.append("a", {}).hash)  # a's cache predates b's rotation
    acked.append(b.append("b", {}).hash)
    acked.append(rotate(a).rotation_event.hash)
    acked.append(b.append("b", {}).hash)
    v = LedgerStore(p).verify()
    assert v.ok and v.length == len(acked) and v.segments == 3
    assert [e.hash for e in LedgerStore(p).events()] == acked


@pytest.mark.parametrize("global_index,segment", [(2, 1), (6, 2), (10, 3)])
def test_tamper_inside_live_closed_segment_names_segment_and_global_index(tmp_path, global_index, segment):
    s, p, hashes = three_segments(tmp_path)
    holder = {1: closed_path_for(p, 1), 2: closed_path_for(p, 2), 3: p}[segment]
    start = {1: 0, 2: 4, 3: 8}[segment]
    edit_line(holder, global_index - start, lambda r: r["payload"].update(tampered=True))
    v = LedgerStore(p).verify()
    assert not v.ok
    assert v.first_break_index == global_index and v.break_segment == segment
    assert v.length == global_index + 1
    assert v.reason.startswith(f"segment {segment}: hash mismatch at index {global_index}:")
    r = runner.invoke(cli_app, ["verify", "--path", str(p)])
    assert r.exit_code == 1
    assert r.stdout.startswith(f"TAMPERED — segment {segment}: hash mismatch at index {global_index}:")


def test_genesis_link_edit_breaks_at_its_first_index(tmp_path):
    s, p, hashes = three_segments(tmp_path)
    # the first event of segment 2 (global 4), re-hashed so ONLY the link is wrong
    edit_line(closed_path_for(p, 2), 0, lambda r: r.update(prev_hash="f" * 64), rehash=True)
    v = LedgerStore(p).verify()
    assert not v.ok and v.first_break_index == 4 and v.break_segment == 2
    assert v.reason.startswith("segment 2: link break at index 4:")


def test_journal_edit_of_archived_head_breaks_live_verify_at_next_segment_first_index(tmp_path):
    s, p, hashes = three_segments(tmp_path / "ledger")
    archive_oldest_for_test(s, tmp_path / "archive")
    archive_oldest_for_test(s, tmp_path / "archive")
    v = LedgerStore(p).verify()
    assert v.ok and v.length == 11 and v.archived_segments == 2 and v.segments == 1
    assert v.verified_events == 3
    jp = journal_path_for(p)
    lines = jp.read_bytes().split(b"\n")
    for k, line in enumerate(lines):
        if line.strip():
            rec = json.loads(line)
            if rec["op"] == "rotate-intent" and rec["n"] == 2:
                rec["head_hash"] = "f" * 64
                lines[k] = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode()
    jp.write_bytes(b"\n".join(lines))
    v = LedgerStore(p).verify()
    assert not v.ok and v.first_break_index == 8 and v.break_segment == 3
    # the live genesis now comes from the edited head: the hash-chained rotation
    # event at global 8 no longer links to it
    assert v.reason.startswith("segment 3: link break at index 8:")
    # an edit that keeps the head but changes another pinned field is named as such
    lines = jp.read_bytes().split(b"\n")
    for k, line in enumerate(lines):
        if line.strip():
            rec = json.loads(line)
            if rec["op"] == "rotate-intent" and rec["n"] == 2:
                rec["head_hash"] = hashes[7]
                rec["anchor"]["anchored_at"] = "2020-01-01T00:00:00+00:00"
                lines[k] = json.dumps(rec, sort_keys=True, separators=(",", ":")).encode()
    jp.write_bytes(b"\n".join(lines))
    v = LedgerStore(p).verify()
    assert not v.ok and v.first_break_index == 8 and v.break_segment == 3
    assert "disagrees with the hash-chained rotation event on anchor (journal edited?)" in v.reason


def test_pre_rotation_anchor_still_verifies(tmp_path):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    evs = fill(s, 5)
    (tmp_path / "anchors.jsonl").write_text(pre_c2_anchor_line(5, evs[-1].hash), encoding="utf-8")
    rotate(s)
    fill(s, 2)
    rotate(s)
    fill(s, 1)
    r = verify_anchors(LedgerStore(p), tmp_path / "anchors.jsonl", public_key_pem=KEY_PUB)
    assert r.ok and r.anchors_checked == 1 and r.signatures_checked == 1
    # a line written now carries no "segment" key: pre-C2 readers still load it
    write_anchor(LedgerStore(p), tmp_path / "anchors2.jsonl", private_key_pem=KEY_PRIV)
    line = (tmp_path / "anchors2.jsonl").read_text(encoding="utf-8").strip()
    assert list(json.loads(line)) == ["anchored_at", "chain_length", "head_hash", "signature"]
    assert json.loads(line)["chain_length"] == 5 + 1 + 2 + 1 + 1


def test_real_scene4_anchor_signed_before_c2_still_verifies():
    fx = FIXTURES / "scene4"
    pub = (fx / "anchor-public.pem").read_text(encoding="ascii")
    r = verify_anchors(LedgerStore(fx / "events.jsonl"), fx / "anchors.jsonl", public_key_pem=pub)
    assert r.ok and r.anchors_checked == 1 and r.signatures_checked == 1
    forged = verify_anchors(LedgerStore(fx / "forged-events.jsonl"), fx / "anchors.jsonl",
                            public_key_pem=pub)
    assert not forged.ok and "history was REWRITTEN" in forged.first_failure


def test_anchor_inside_archived_segment_is_explicit_failure(tmp_path):
    s, p, hashes = three_segments(tmp_path / "ledger")
    write_anchor(s, tmp_path / "live.jsonl", private_key_pem=KEY_PRIV)  # length 11: live
    archive_oldest_for_test(s, tmp_path / "archive")
    assert verify_anchors(LedgerStore(p), tmp_path / "live.jsonl", public_key_pem=KEY_PUB).ok
    (tmp_path / "early.jsonl").write_text(pre_c2_anchor_line(3, hashes[2]), encoding="utf-8")
    r = verify_anchors(LedgerStore(p), tmp_path / "early.jsonl", public_key_pem=KEY_PUB)
    assert not r.ok and r.signatures_checked == 1
    assert "archived segment 1" in r.first_failure
    assert str(tmp_path / "archive" / "events-1.jsonl") in r.first_failure
    # a live position is unaffected; hash_at says why
    assert LedgerStore(p).hash_at(2) == "archived" and LedgerStore(p).hash_at(5) == hashes[5]
    assert LedgerStore(p).hash_at(11) is None


def test_events_agent_id_spans_segments(tmp_path):
    s, p, hashes = three_segments(tmp_path)
    client = TestClient(create_app(store=LedgerStore(p)))
    a0 = client.get("/events", params={"agent_id": "a0"}).json()
    # fill() alternates a0/a1: seg1 idx 0,2 ; seg2 idx 5,7 ; open idx 9
    assert [e["hash"] for e in a0] == [hashes[i] for i in (0, 2, 5, 7, 9)]
    last3 = client.get("/events", params={"limit": 3}).json()
    assert [e["hash"] for e in last3] == hashes[-3:]
    rotations = client.get("/events", params={"event_type": "ledger.segment.rotated"}).json()
    assert [e["hash"] for e in rotations] == [hashes[4], hashes[8]]


@pytest.mark.parametrize("key_state", ["unset", "missing-file", "directory", "garbage", "not-ed25519"])
def test_rotate_without_key_503(tmp_path, monkeypatch, key_state):
    """No usable FIELD_LEDGER_ANCHOR_KEY => 503, nothing written, and the
    process keeps serving (a key-load failure is never a process exit)."""
    p = tmp_path / "ledger" / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 3)
    if key_state == "unset":
        monkeypatch.delenv("FIELD_LEDGER_ANCHOR_KEY", raising=False)
    else:
        target = {
            "missing-file": tmp_path / "keys" / "absent.pem",
            "directory": tmp_path / "keys",
            "garbage": tmp_path / "keys" / "garbage.pem",
            "not-ed25519": tmp_path / "keys" / "ec.pem",
        }[key_state]
        (tmp_path / "keys").mkdir()
        if key_state == "garbage":
            target.write_bytes(b"-----BEGIN PRIVATE KEY-----\nnot a key\n-----END PRIVATE KEY-----\n")
        if key_state == "not-ed25519":
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ec

            target.write_bytes(ec.generate_private_key(ec.SECP256R1()).private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()))
        monkeypatch.setenv("FIELD_LEDGER_ANCHOR_KEY", str(target))
    before = listing(p.parent)
    client = TestClient(create_app(store=s))
    r = client.post("/rotate", json={"operator": "ops", "reason": "quarterly"})
    assert r.status_code == 503, r.text
    detail = r.json()["detail"]
    if key_state == "unset":
        assert detail == "no anchor key configured"
    else:
        assert detail.startswith(("anchor key unreadable", "anchor key unusable"))
        assert "BEGIN" not in detail and "not a key" not in detail
    assert listing(p.parent) == before
    assert client.get("/health").json()["event_count"] == 3
    assert client.post("/events", json={"event_type": "still-serving"}).status_code == 201
    # the served app also BUILDS with a broken key configured (read per request)
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    assert TestClient(create_app()).get("/health").status_code == 200


def test_field_verify_chain_single_file_documented(tmp_path):
    from field_core.cli import app as field_app

    single = tmp_path / "single" / "events.jsonl"
    fill(LedgerStore(single), 5)
    r = runner.invoke(field_app, ["verify-chain", str(single)])
    assert r.exit_code == 0 and r.stdout == "OK — chain intact over 5 events\n" and r.stderr == ""

    s, p, hashes = three_segments(tmp_path / "rotated")
    r = runner.invoke(field_app, ["verify-chain", str(p)])
    assert r.exit_code == 1
    assert r.stdout.startswith("TAMPERED — link break at index 0:")
    assert r.stderr.startswith(f"note: {p} is the open segment of a rotated ledger")
    assert "ledger verify --path" in r.stderr
    r = runner.invoke(field_app, ["verify-chain", str(p), "--genesis", hashes[7]])
    assert r.exit_code == 0 and r.stdout == "OK — chain intact over 3 events\n"


# ------------------------------------------------ critique / judge failure modes


def test_rotate_refuses_existing_closed_name(tmp_path):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 3)
    squatter = closed_path_for(p, 1)
    squatter.write_bytes(b"foreign bytes\n")
    with pytest.raises(RotationRefused):
        rotate(s)
    assert squatter.read_bytes() == b"foreign bytes\n"
    assert not journal_path_for(p).exists()  # refused at plan time: nothing journaled
    assert LedgerStore(p).verify().ok and LedgerStore(p).verify().length == 3
    # appearing between plan and rename (a racing process): intent + abort, P intact
    squatter.unlink()
    s2 = LedgerStore(p)
    orig = s2._rename_with_retry

    def racing(src, dst):
        squatter.write_bytes(b"raced in\n")
        return orig(src, dst)

    s2._rename_with_retry = racing
    with pytest.raises(RotationRefused):
        rotate(s2)
    assert squatter.read_bytes() == b"raced in\n"
    assert [r["op"] for r in journal_records(p)] == ["rotate-intent", "rotate-abort"]
    assert not store_mod.rotating_tmp_for(p).exists()
    client = TestClient(create_app(store=LedgerStore(p)))
    # a journal holding only an aborted intent: nothing ever rotated, still single-file
    assert client.get("/verify").json() == {"ok": True, "length": 3, "first_break_index": None,
                                            "reason": None}


_HOLDER = """import sys, time
fh = open(sys.argv[1], 'rb')
first = fh.read(64)
print('opened', flush=True)
sys.stdin.readline()
rest = fh.read()
print(len(first + rest), flush=True)
"""


def _foreign_holder(p: Path):
    proc = subprocess.Popen([sys.executable, "-c", _HOLDER, str(p)], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "opened"
    return proc


@pytest.mark.skipif(os.name != "nt", reason="Windows sharing semantics (WinError 32)")
def test_foreign_plain_handle_rotation_503_nothing_renamed(tmp_path, monkeypatch):
    p = tmp_path / "ledger" / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 5)
    size_before = p.stat().st_size
    monkeypatch.setenv("FIELD_LEDGER_ANCHOR_KEY", str(_key_file(tmp_path)))
    holder = _foreign_holder(p)
    client = TestClient(create_app(store=s))
    try:
        t0 = time.monotonic()
        with pytest.raises(LedgerBusy, match="held open by another process; nothing renamed"):
            rotate(s)
        took = time.monotonic() - t0
        assert 0.35 <= took < 5.0, took  # 5 attempts x 100 ms, then 503
        assert not closed_path_for(p, 1).exists() and p.stat().st_size == size_before
        assert [r["op"] for r in journal_records(p)] == ["rotate-intent", "rotate-abort"]
        r = client.post("/rotate", json={"operator": "o", "reason": "r"})
        assert r.status_code == 503 and r.json()["detail"].startswith("ledger busy:")
        assert client.post("/events", json={"event_type": "during-hold"}).status_code == 201
        assert client.get("/health").json()["event_count"] == 6
    finally:
        holder.communicate("\n", timeout=30)
    assert [r["op"] for r in journal_records(p)] == ["rotate-intent", "rotate-abort"] * 2
    v = LedgerStore(p).verify()
    assert v.ok and v.length == 6 and v.segments is None  # nothing rotated: still single-file
    assert rotate(LedgerStore(p)).segment == 1  # released: the next rotation succeeds


@pytest.mark.skipif(os.name == "nt", reason="POSIX rename over an open handle")
def test_foreign_plain_handle_rotation_succeeds(tmp_path):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 5)
    size_before = p.stat().st_size
    holder = _foreign_holder(p)
    rotate(s)
    out, _ = holder.communicate("\n", timeout=30)
    assert int(out.strip()) == size_before  # the holder read its old inode
    assert LedgerStore(p).verify().ok


def test_windows_share_delete_readers_never_block_or_fail_rotation(tmp_path):
    """4 reader threads loop verify()/events() on fresh and shared stores while
    rotations run (40; the spec's 100 with FIELD_SLOW_TESTS=1): no reader
    exception, no short ok, no LedgerBusy."""
    rotations = 100 if SLOW else 40
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 10)
    acked = [10]
    stop = threading.Event()
    bad: list = []
    reads = [0]

    def reader(k):
        while not stop.is_set():
            low = acked[0]
            st = LedgerStore(p) if k % 2 == 0 else s
            try:
                if k < 2:
                    v = st.verify()
                    if not v.ok:
                        bad.append(("not ok", v.reason))
                    elif v.length < low:
                        bad.append(("short ok", v.length, low))
                else:
                    n = len(st.events())
                    if n < low:
                        bad.append(("short events", n, low))
            except Exception as exc:  # noqa: BLE001
                bad.append(("exception", repr(exc)))
            reads[0] += 1

    threads = [threading.Thread(target=reader, args=(k,)) for k in range(4)]
    for t in threads:
        t.start()
    errors = []
    try:
        for _ in range(rotations):
            try:
                s.append("w", {})
                acked[0] += 1
                rotate(s)
                acked[0] += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))
    finally:
        stop.set()
        for t in threads:
            t.join(60)
    assert errors == [] and bad == [], (errors[:3], bad[:3])
    assert reads[0] > 0
    v = LedgerStore(p).verify()
    assert v.ok and v.length == acked[0] and v.segments == rotations + 1


def test_write_anchor_during_rotation_never_zero(tmp_path):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 30)
    stop = threading.Event()
    anchored: list[int] = []
    floor = [30]

    def anchorer():
        store = LedgerStore(p)
        while not stop.is_set():
            low = floor[0]
            a = write_anchor(store, tmp_path / "anchors.jsonl", private_key_pem=KEY_PRIV)
            if a.chain_length < low:
                anchored.append(("SHORT", a.chain_length, low))
            else:
                anchored.append(a.chain_length)

    t = threading.Thread(target=anchorer)
    t.start()
    try:
        for _ in range(25):
            s.append("w", {})
            floor[0] += 1
            rotate(s)
            floor[0] += 1
    finally:
        stop.set()
        t.join(60)
    assert anchored and not [a for a in anchored if isinstance(a, tuple)], anchored[:5]
    assert verify_anchors(LedgerStore(p), tmp_path / "anchors.jsonl", public_key_pem=KEY_PUB).ok


def test_rotation_reenters_writer_lock(tmp_path):
    s = LedgerStore(tmp_path / "events.jsonl")
    fill(s, 3)
    out: dict = {}

    def run():
        try:
            with s._writer():
                with s._writer():
                    out["rot"] = rotate(s)
                    out["app"] = s.append("inside", {})
                    out["len"] = s.global_length()
                    out["anchor"] = write_anchor(s, tmp_path / "a.jsonl", private_key_pem=KEY_PRIV)
        except Exception as exc:  # noqa: BLE001
            out["exc"] = repr(exc)

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(10)
    assert not t.is_alive(), "DEADLOCK: rotation blocked on its own writer lock"
    assert "exc" not in out, out
    assert out["app"].prev_hash == out["rot"].rotation_event.hash
    assert out["len"] == 5 and out["anchor"].chain_length == 5
    assert s.verify().ok and s.verify().length == 5


def test_plain_lock_control_deadlocks(tmp_path):
    """Negative control: the same rotation with a non-reentrant Lock hangs,
    so the RLock is load-bearing."""
    s = LedgerStore(tmp_path / "events.jsonl")
    fill(s, 2)
    s._lock = threading.Lock()
    t = threading.Thread(target=lambda: rotate(s), daemon=True)
    t.start()
    t.join(2)
    assert t.is_alive()


def test_signed_view_excludes_segment_when_none(tmp_path):
    fx = FIXTURES / "scene4"
    pub = (fx / "anchor-public.pem").read_text(encoding="ascii")
    rec = AnchorRecord.model_validate_json((fx / "anchors.jsonl").read_text(encoding="utf-8").strip())
    assert verify_manifest(signed_view(rec), rec.signature, pub)
    naive = rec.model_dump(exclude={"signature"})  # carries "segment": None
    assert "segment" in naive and not verify_manifest(naive, rec.signature, pub)
    s = LedgerStore(tmp_path / "events.jsonl")
    fill(s, 3)
    anchor = AnchorRecord.model_validate(rotate(s).anchor)
    assert anchor.segment == 1 and anchor.chain_length == 3
    assert verify_manifest(signed_view(anchor), anchor.signature, KEY_PUB)
    moved = anchor.model_copy(update={"segment": 2})
    assert not verify_manifest(signed_view(moved), moved.signature, KEY_PUB)
    (tmp_path / "rot.jsonl").write_text(moved.model_dump_json() + "\n", encoding="utf-8")
    r = verify_anchors(s, tmp_path / "rot.jsonl", public_key_pem=KEY_PUB)
    assert not r.ok and "signature invalid" in r.first_failure


def test_fresh_path_open_and_reads_write_nothing(tmp_path):
    d = tmp_path / "ledger"
    d.mkdir()
    p = d / "e.jsonl"
    s = LedgerStore(p)
    client = TestClient(create_app(store=s))
    assert client.get("/health").json()["event_count"] == 0
    assert client.get("/events").json() == []
    assert client.get("/verify").json() == {"ok": True, "length": 0, "first_break_index": None,
                                            "reason": None}
    assert s.hash_at(0) is None and s.global_length() == 0 and s.head_hash == GENESIS_HASH
    assert runner.invoke(cli_app, ["verify", "--path", str(p)]).exit_code == 0
    assert list(d.iterdir()) == []
    fill(s, 4)
    assert sorted(x.name for x in d.iterdir()) == [".e.jsonl.lock", "e.jsonl"]
    before = listing(d)
    s2 = LedgerStore(p)
    TestClient(create_app(store=s2)).get("/health")
    s2.verify(), s2.events(limit=2), list(s2.iter_events()), s2.snapshot(), s2.needs_reconcile()
    assert runner.invoke(cli_app, ["verify", "--path", str(p)]).exit_code == 0
    assert listing(d) == before


def test_single_file_line_n_is_event_n(tmp_path):
    p = tmp_path / "e.jsonl"
    s = LedgerStore(p)
    evs = fill(s, 7)
    assert [json.loads(x)["hash"] for x in p.read_text(encoding="utf-8").splitlines()] == [
        e.hash for e in evs
    ]
    lines = p.read_text(encoding="utf-8").splitlines()
    mutated = json.loads(lines[3])
    mutated["payload"]["n"] = 99
    for name, content in {
        "intact": lines,
        "mutated": lines[:3] + [json.dumps(mutated)] + lines[4:],
        "deleted": lines[:1] + lines[2:],
        "empty": [],
    }.items():
        f = tmp_path / f"{name}.jsonl"
        f.write_text("".join(x + "\n" for x in content), encoding="utf-8")
        mine = LedgerStore(f).verify().model_dump()
        from sealed_ledger.store import _parse_events

        pre_c2 = verify_chain(_parse_events(f.read_bytes())).model_dump()  # what HEAD's verify() was
        assert set(mine) == {"ok", "length", "first_break_index", "reason"}
        assert mine == pre_c2, name


@pytest.mark.parametrize("damage", ["truncate_closed_tail", "extend_closed", "delete_closed",
                                    "delete_open", "empty_open"])
def test_missing_truncated_or_extended_segments_never_verify_ok(tmp_path, damage):
    s, p, hashes = three_segments(tmp_path)
    seg1 = closed_path_for(p, 1)
    lines = seg1.read_text(encoding="utf-8").splitlines()
    if damage == "truncate_closed_tail":  # the links inside the segment stay intact
        seg1.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")
    elif damage == "extend_closed":
        from field_core.ledger import make_event

        extra = make_event("smuggled", {}, prev_hash=hashes[3])
        seg1.write_text("\n".join(lines) + "\n" + extra.model_dump_json() + "\n", encoding="utf-8")
    elif damage == "delete_closed":
        seg1.unlink()
    elif damage == "delete_open":
        p.unlink()
    else:
        p.write_text("", encoding="utf-8")
    v = LedgerStore(p).verify()
    assert not v.ok, (damage, v)
    assert v.break_segment is not None and v.reason.startswith(f"segment {v.break_segment}:")
    expected = {"truncate_closed_tail": (1, 2), "extend_closed": (1, 4), "delete_closed": (1, 0),
                "delete_open": (3, 8), "empty_open": (3, 8)}[damage]
    assert (v.break_segment, v.first_break_index) == expected, v


def test_torn_in_flight_last_line_is_reread_not_believed(tmp_path, monkeypatch):
    """G5, deterministic: the open segment is read with its last line half
    copied (as Linux page-cache extension can show) and complete on a later
    read. The snapshot must re-read and return every event — not raise."""
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 4)
    full = p.read_bytes()
    torn = full[: full.rstrip(b"\r\n").rfind(b"\n") + 1 + 30]
    reads = [0]
    real_open = store_mod.open_shared

    def half_copied_twice(path):
        fh = real_open(path)
        if Path(path) == p and reads[0] < 2:
            reads[0] += 1
            import io

            data = fh.read()
            fh.close()
            return io.BytesIO(torn if data == full else data)
        return fh

    monkeypatch.setattr(store_mod, "open_shared", half_copied_twice)
    fresh_events = LedgerStore(p).events()
    assert len(fresh_events) == 4 and reads[0] == 2
    # a torn tail that PERSISTS is still an error, exactly as before C2
    p.write_bytes(torn)
    monkeypatch.setattr(store_mod, "open_shared", real_open)
    with pytest.raises(json.JSONDecodeError):
        LedgerStore(p)


def test_deleting_journal_is_loud(tmp_path):
    s, p, hashes = three_segments(tmp_path)
    journal_path_for(p).unlink()
    v = LedgerStore(p).verify()
    assert not v.ok and v.first_break_index == 0 and v.reason.startswith("link break at index 0:")


def test_torn_last_line_raises_as_today(tmp_path):
    p = tmp_path / "e.jsonl"
    fill(LedgerStore(p), 5)
    raw = p.read_bytes()
    last_start = raw.rstrip(b"\r\n").rfind(b"\n") + 1
    p.write_bytes(raw[: last_start + 40])
    with pytest.raises(json.JSONDecodeError):
        LedgerStore(p)
    r = subprocess.run([sys.executable, "-m", "sealed_ledger.cli", "verify", "--path", str(p)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=120, env=dict(os.environ, PYTHONIOENCODING="utf-8"))
    assert r.returncode == 1 and "JSONDecodeError" in r.stderr


def test_chain_verification_json_keys_single_file_and_segmented(tmp_path):
    s = LedgerStore(tmp_path / "one" / "e.jsonl")
    fill(s, 2)
    client = TestClient(create_app(store=s))
    assert set(client.get("/verify").json()) == {"ok", "length", "first_break_index", "reason"}
    summary = client.post("/export", params={"out_dir": str(tmp_path / "x1")}).json()
    assert set(summary["verification"]) == {"ok", "length", "first_break_index", "reason"}
    rotate(s)
    served = client.get("/verify").json()
    assert len(served) == 8 and served["segments"] == 2
    assert ChainVerification.model_validate(served).model_dump() == served
    assert client.get("/openapi.json").json()["components"]["schemas"]["ChainVerification"][
        "properties"
    ].keys() >= {"ok", "length", "segments", "break_segment"}


# ------------------------------------------------------------------ journal


def test_torn_journal_tail_is_ignored_by_readers_and_truncated_by_the_next_write(tmp_path):
    s, p, hashes = three_segments(tmp_path)
    jp = journal_path_for(p)
    good = jp.read_bytes()
    jp.write_bytes(good + b'{"op":"rotate-intent","format":"field-ledger-')
    fresh = LedgerStore(p)
    assert fresh.verify().ok and fresh.verify().length == 11
    assert fresh.needs_reconcile()
    assert jp.read_bytes() != good  # reading changed nothing
    fresh.append("after", {})
    assert jp.read_bytes() == good and not fresh.needs_reconcile()
    assert LedgerStore(p).verify().length == 12


def test_invalid_complete_journal_line_is_a_break_and_refuses_writes(tmp_path):
    s, p, hashes = three_segments(tmp_path)
    jp = journal_path_for(p)
    jp.write_bytes(jp.read_bytes() + b'{"op":"rotate-commit","n":9}\n')
    v = LedgerStore(p).verify()
    assert not v.ok and v.break_segment == 3 and v.first_break_index == 8
    assert "segments journal line 5 invalid" in v.reason
    client = TestClient(create_app(store=LedgerStore(p)), raise_server_exceptions=False)
    r = client.post("/events", json={"event_type": "x"})
    assert r.status_code == 500 and "segments journal line 5 invalid" in r.json()["detail"]
    assert client.get("/health").status_code == 200
    with pytest.raises(LedgerCorrupt):
        rotate(LedgerStore(p))


# ----------------------------------------------------------- busy readers


def _never_consistent(monkeypatch, store_cls_timeout: float = 0.2):
    counter = [0]
    real = store_mod.read_shared

    def flapping(path):
        data = real(path)
        if str(path).endswith(".segments.journal"):
            counter[0] += 1
            return (data or b"") + b"\n" * (counter[0] % 2)
        return data

    monkeypatch.setattr(store_mod, "read_shared", flapping)
    monkeypatch.setattr(LedgerStore, "SNAPSHOT_TIMEOUT_S", store_cls_timeout)


def test_busy_snapshot_is_never_reported_as_tampering(tmp_path, monkeypatch):
    s, p, hashes = three_segments(tmp_path)
    client = TestClient(create_app(store=s))
    _never_consistent(monkeypatch)
    v = client.get("/verify")
    assert v.status_code == 200
    body = v.json()
    assert body["ok"] is False and body["reason"].startswith("ledger busy: no consistent snapshot")
    assert client.get("/events").status_code == 503
    assert client.post("/export", params={"out_dir": str(tmp_path / "x")}).status_code == 503
    assert client.get("/health").status_code == 200  # never waits on a snapshot it cannot get
    r = runner.invoke(cli_app, ["verify", "--path", str(p)])
    assert r.exit_code == 4 and r.stderr.startswith("BUSY — ledger busy:") and "TAMPERED" not in r.output
    assert client.post("/events", json={"event_type": "appends-are-not-readers"}).status_code == 201


def test_cli_verify_busy_after_open_is_exit_4_not_tampered(tmp_path, monkeypatch):
    s, p, hashes = three_segments(tmp_path)
    monkeypatch.setattr(LedgerStore, "verify", lambda self: ChainVerification(
        ok=False, length=0, reason="ledger busy: no consistent snapshot after 90 attempts"))
    r = runner.invoke(cli_app, ["verify", "--path", str(p)])
    assert r.exit_code == 4 and "TAMPERED" not in r.output
    assert r.stderr == "BUSY — ledger busy: no consistent snapshot after 90 attempts; retry\n"


# ------------------------------------------------------------------ /health


def test_health_is_cached_global_and_takes_no_lock(tmp_path):
    s, p, hashes = three_segments(tmp_path / "ledger")
    assert s._health[2] == s._disk_key()  # O(1) path: the cache key matches the disk
    calls = []
    real = LedgerStore._take_snapshot
    s._take_snapshot = lambda *a, **k: calls.append(1) or real(s, *a, **k)
    client = TestClient(create_app(store=s))
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
        assert h["event_count"] == 11 and h["head_hash"] == hashes[-1] and calls == []
    finally:
        release.set()
        t.join(10)
    other = LedgerStore(p)  # another writer changes the files behind s's back
    other.append("elsewhere", {})
    h = client.get("/health").json()
    assert h["event_count"] == 12 and len(calls) == 1
    client.get("/health")
    assert len(calls) == 1  # the out-of-band count is cached per disk key
    archive_oldest_for_test(other, tmp_path / "archive")
    h = client.get("/health").json()
    assert h["event_count"] == 12 and h["earliest_live_index"] == 4
    assert h["earliest_live_ts"] == LedgerStore(p).events()[0].ts


# ------------------------------------------------------------ served /rotate


def test_served_rotate_route(tmp_path, monkeypatch):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    monkeypatch.setenv("FIELD_LEDGER_ANCHOR_KEY", str(_key_file(tmp_path)))
    client = TestClient(create_app(store=s))
    assert client.post("/rotate", json={"operator": "ops", "reason": "q3"}).status_code == 409  # empty
    assert client.post("/rotate", json={"operator": "", "reason": "q3"}).status_code == 422
    assert client.post("/rotate", json={"operator": "   ", "reason": "q3"}).status_code == 422
    assert client.post("/rotate", json={"operator": "ops"}).status_code == 422
    fill(s, 4)
    r = client.post("/rotate", json={"operator": "ops", "reason": "q3 retention"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["segment"], body["file"], body["start_index"], body["end_index"]) == (1, "events-1.jsonl", 0, 3)
    rot = body["rotation_event"]
    assert rot["payload"]["operator"] == "ops" and rot["payload"]["reason"] == "q3 retention"
    assert rot["payload"]["anchor"] == body["anchor"]
    anchor = AnchorRecord.model_validate(body["anchor"])
    assert anchor.chain_length == 4 and anchor.segment == 1
    assert verify_manifest(signed_view(anchor), anchor.signature, KEY_PUB)
    assert client.get("/health").json()["event_count"] == 5
    types = [e["event_type"] for e in client.get("/events").json()]
    assert types.count("ledger.segment.rotated") == 1 and len(types) == 5  # ledgered once


def test_served_startup_reconciles_only_a_crashed_rotation(tmp_path, monkeypatch):
    data = tmp_path / "data"
    p = data / "ledger" / "events.jsonl"
    fill(LedgerStore(p), 3)
    monkeypatch.setenv("FIELD_DATA_DIR", str(data))
    before = listing(p.parent)
    TestClient(create_app()).get("/health")
    assert listing(p.parent) == before  # a clean ledger is never written at startup
    key = _key_file(tmp_path)
    code = ("import sys; from sealed_ledger.store import LedgerStore; "
            "LedgerStore(sys.argv[1]).rotate(private_key_pem=open(sys.argv[2]).read(), "
            "operator='o', reason='r')")
    r = subprocess.run([sys.executable, "-c", code, str(p), str(key)], capture_output=True,
                       text=True, timeout=120,
                       env=dict(os.environ, FIELD_LEDGER_CRASH_AT="rotate.after_rename"))
    assert r.returncode == 77, r.stderr
    assert not p.exists() and LedgerStore(p).needs_reconcile()
    client = TestClient(create_app())
    assert [x["op"] for x in journal_records(p)] == ["rotate-intent", "rotate-commit"]
    assert journal_records(p)[1]["recovered"] is True
    v = client.get("/verify").json()
    assert v["ok"] and v["length"] == 4 and v["segments"] == 2


# ---------------------------------------------------------------------- CLI


def test_cli_verify_dispatch_closed_segment_genesis_and_anchors(tmp_path):
    s, p, hashes = three_segments(tmp_path)
    seg2 = closed_path_for(p, 2)
    r = runner.invoke(cli_app, ["verify", "--path", str(seg2)])
    assert r.exit_code == 0, r.output
    assert r.stdout == "OK — segment 2 of events.jsonl intact over 4 events (global 4..7)\n"
    r = runner.invoke(cli_app, ["verify", "--path", str(seg2), "--anchors", str(tmp_path / "a.jsonl")])
    assert r.exit_code == 2
    r = runner.invoke(cli_app, ["verify", "--path", str(seg2), "--genesis", hashes[3]])
    assert r.exit_code == 0 and r.stdout == "OK — chain intact over 4 events\n"
    r = runner.invoke(cli_app, ["verify", "--path", str(seg2), "--genesis", GENESIS_HASH])
    assert r.exit_code == 1 and r.stdout.startswith("TAMPERED — link break at index 0:")
    edit_line(seg2, 2, lambda rec: rec["payload"].update(n=42))
    r = runner.invoke(cli_app, ["verify", "--path", str(seg2)])
    assert r.exit_code == 1 and r.stdout.startswith("TAMPERED — segment 2: hash mismatch at index 6:")
    # a file that only LOOKS like a closed segment (no journal entry) is single-file
    lookalike = tmp_path / "solo" / "events-1.jsonl"
    fill(LedgerStore(lookalike), 2)
    r = runner.invoke(cli_app, ["verify", "--path", str(lookalike)])
    assert r.exit_code == 0 and r.stdout == "OK — chain intact over 2 events\n"


def _serve_in_thread(app):
    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    return server, thread, port


def test_cli_rotate_offline_served_and_refusals(tmp_path, monkeypatch):
    p = tmp_path / "ledger" / "events.jsonl"
    s = LedgerStore(p)
    fill(s, 3)
    key = _key_file(tmp_path)
    monkeypatch.delenv("FIELD_LEDGER_URL", raising=False)
    monkeypatch.delenv("FIELD_LEDGER_ANCHOR_KEY", raising=False)
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    r = runner.invoke(cli_app, ["rotate", "--operator", "o", "--reason", "r"])
    assert r.exit_code == 2 and "set FIELD_LEDGER_URL, or pass --offline" in r.stderr
    r = runner.invoke(cli_app, ["rotate", "--operator", "o", "--reason", "r", "--offline", "--path", str(p)])
    assert r.exit_code == 2 and "no anchor key configured" in r.stderr
    r = runner.invoke(cli_app, ["rotate", "--operator", " ", "--reason", "r", "--offline",
                                "--path", str(p), "--key", str(key)])
    assert r.exit_code == 2
    assert not journal_path_for(p).exists()
    r = runner.invoke(cli_app, ["rotate", "--operator", "o", "--reason", "r", "--offline",
                                "--path", str(p), "--key", str(key),
                                "--anchors", str(tmp_path / "offbox.jsonl")])
    assert r.exit_code == 0, r.output
    assert json.loads(r.stdout)["segment"] == 1
    assert verify_anchors(LedgerStore(p), tmp_path / "offbox.jsonl", public_key_pem=KEY_PUB).ok
    r = runner.invoke(cli_app, ["rotate", "--operator", "o", "--reason", "r", "--offline",
                                "--path", str(p), "--key", str(key)])
    assert r.exit_code == 0  # the rotation event alone is a non-empty open segment

    # served: FIELD_LEDGER_URL with a path prefix, as behind the estate proxy
    outer = FastAPI()
    served_store = LedgerStore(p)
    outer.mount("/ledger", create_app(store=served_store))
    server, thread, port = _serve_in_thread(outer)
    try:
        monkeypatch.setenv("FIELD_LEDGER_URL", f"http://127.0.0.1:{port}/ledger")
        r = runner.invoke(cli_app, ["rotate", "--operator", "o", "--reason", "r"])
        assert r.exit_code == 2 and "no anchor key configured" in r.stderr  # the SERVICE's key
        monkeypatch.setenv("FIELD_LEDGER_ANCHOR_KEY", str(key))
        served_store.append("x", {})
        r = runner.invoke(cli_app, ["rotate", "--operator", "o", "--reason", "served",
                                    "--anchors", str(tmp_path / "offbox.jsonl")])
        assert r.exit_code == 0, r.output
        assert json.loads(r.stdout)["segment"] == 3
        r = runner.invoke(cli_app, ["rotate", "--operator", "o", "--reason", "r", "--key", str(key)])
        assert r.exit_code == 2 and "only with --offline" in r.stderr
    finally:
        server.should_exit = True
        thread.join(30)
    v = LedgerStore(p).verify()
    assert v.ok and v.segments == 4
    assert verify_anchors(LedgerStore(p), tmp_path / "offbox.jsonl", public_key_pem=KEY_PUB).signatures_checked == 2


# ------------------------------------------------------------------- export


def test_export_of_a_rotated_ledger_uses_global_indices(tmp_path):
    s, p, hashes = three_segments(tmp_path / "ledger")
    summary = s.export(tmp_path / "exports")
    assert summary.indices == list(range(11)) and summary.head_index == 10
    assert summary.verification.segments == 3
    res = verify_bundle(summary.bundle_dir)
    assert res.ok and res.unfiltered and res.contiguous and res.archived_prefix == 0
    r = runner.invoke(cli_app, ["verify-export", summary.bundle_dir])
    assert "filters: none — every index 0..10 is exported (verified)" in r.stdout
    filtered = s.export(tmp_path / "exports", agent_id="a1")
    assert filtered.indices == [1, 3, 6, 10]
    assert verify_bundle(filtered.bundle_dir).ok


def _bundle_file(bundle: str, name: str) -> Path:
    return Path(bundle) / name


def test_export_after_archival_starts_at_the_earliest_live_index(tmp_path, monkeypatch):
    s, p, hashes = three_segments(tmp_path / "ledger")
    archive_oldest_for_test(s, tmp_path / "archive")
    archive_oldest_for_test(s, tmp_path / "archive")
    summary = s.export(tmp_path / "exports")
    assert summary.indices == [8, 9, 10] and summary.first_index == 8 and summary.head_index == 10
    assert json.loads(_bundle_file(summary.bundle_dir, "chain_proof.json").read_text())["first_prev_hash"] == hashes[7]
    res = verify_bundle(summary.bundle_dir)
    assert res.ok and res.unfiltered and res.archived_prefix == 8, res
    r = runner.invoke(cli_app, ["verify-export", summary.bundle_dir])
    assert r.exit_code == 0, r.output
    assert ("filters: none — every live index 8..10 is exported (verified); indices 0..7 are "
            "archived — verify them with ledger verify --path <archived file>") in r.stdout
    # dropping the first live event (the rotation event) is still caught
    events = _bundle_file(summary.bundle_dir, "events.jsonl")
    lines = events.read_text(encoding="utf-8").splitlines()
    events.write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")
    bad = verify_bundle(summary.bundle_dir)
    assert not bad.ok and bad.first_failing_index == 8


def _claim_archived_prefix(bundle: Path, drop: int, archived_segments: int) -> None:
    """Edit an unsigned unfiltered bundle: drop the first ``drop`` events and
    re-edit every count, index and the verification to claim them archived."""
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


def test_claimed_archived_prefix_must_end_at_a_rotation_event(tmp_path):
    """Dropping leading events of a never-rotated ledger and claiming them
    archived fails: the first live event after a real archived prefix is always
    the rotation event that closed it. A prefix with no archived segment fails too."""
    s = LedgerStore(tmp_path / "ledger" / "events.jsonl")
    fill(s, 8)
    for drop, archived, why in ((3, 1, "should be the rotation event closing archived segment 1"),
                                (3, 0, "claims 0 archived segment(s) but 3 archived event(s)")):
        bundle = Path(s.export(tmp_path / f"x-{drop}-{archived}").bundle_dir)
        assert verify_bundle(bundle).ok
        _claim_archived_prefix(bundle, drop, archived)
        res = verify_bundle(bundle)
        assert not res.ok and why in res.reason, res


def test_unsigned_bundle_can_claim_an_archived_prefix_but_not_under_signature(tmp_path):
    """The documented limit: on a rotated (NOT archived) ledger, an editor of an
    unsigned unfiltered bundle can drop segment 1 and claim it archived — the
    verifier then PRINTS the archived prefix. Under a signature it fails."""
    s, p, hashes = three_segments(tmp_path / "ledger")
    priv, pub = generate_keypair()
    for signed in (False, True):
        summary = s.export(tmp_path / f"exports-{signed}", private_key_pem=priv if signed else None)
        b = Path(summary.bundle_dir)
        lines = (b / "events.jsonl").read_text(encoding="utf-8").splitlines()
        (b / "events.jsonl").write_text("\n".join(lines[4:]) + "\n", encoding="utf-8")
        sm = json.loads((b / "summary.json").read_text(encoding="utf-8"))
        cp = json.loads((b / "chain_proof.json").read_text(encoding="utf-8"))
        for doc in (sm, cp):
            doc["verification"].update(verified_events=7, archived_segments=1)
            doc["first_index"] = 4
        sm["indices"] = list(range(4, 11))
        sm["event_count"] = 7
        kept = [json.loads(x) for x in lines[4:]]
        sm["event_types"] = {}
        sm["agents"] = {}
        for rec in kept:
            sm["event_types"][rec["event_type"]] = sm["event_types"].get(rec["event_type"], 0) + 1
            key = rec["agent_id"] or "<none>"
            sm["agents"][key] = sm["agents"].get(key, 0) + 1
        sm["first_ts"] = kept[0]["ts"]
        cp["first_prev_hash"] = hashes[3]
        cp["spine"] = cp["spine"][4:]
        (b / "summary.json").write_text(json.dumps(sm, indent=2), encoding="utf-8")
        (b / "chain_proof.json").write_text(json.dumps(cp, indent=2), encoding="utf-8")
        if signed:
            res = verify_bundle(b, public_key_pem=pub)
            assert not res.ok and "signature invalid" in res.reason
        else:
            res = verify_bundle(b)
            assert res.ok and res.archived_prefix == 4
            out = runner.invoke(cli_app, ["verify-export", str(b)]).stdout
            assert "indices 0..3 are archived" in out and "spine unverified (unsigned)" in out
