"""B-GL-verify-cache-key: does GET /verify (LedgerStore.verify -> _verified -> Snapshot.verify) depend on anything
beyond the BYTES the T7 verify-cache key holds (layout + every live segment's bytes), once T8 stopped answering
from the cache for an archived ledger?

Every input verify() reads is enumerated in the note at the end of this module. Each test below warms the cache
(two verify() calls, the second the cached one), changes ONE input while the cache-key bytes are unchanged (or,
for the key's own parts, changes them), and requires verify() to equal an UNCACHED verification of the very
same read AND a fresh store's verdict. Where the input is not read by verify(), the test also pins that the
verdict did not move.
"""

from __future__ import annotations

import json
import os
from datetime import datetime as real_datetime

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

import sealed_ledger.store as store_mod
from field_core.signing import generate_keypair
from sealed_ledger.api import create_app
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import LedgerStore, SigningConfig, journal_path_for

from ledger_c2_support import archive_oldest_for_test, fill, journal_records, three_segments

runner = CliRunner()


def uncached_verify(store: LedgerStore):
    """verification of the bytes and files as they are now, with no verify cache and no parse cache."""
    snap = store._take_snapshot(tolerant=True)
    return store_mod.Snapshot(snap.layout, snap.raw, 1, tolerant=True).verify()


def warm(store: LedgerStore):
    first = store.verify()
    assert first.ok, first.reason
    assert store.verify() == first          # the second answer is the cached one
    return first


def agrees(store: LedgerStore, path) -> object:
    """verify() == uncached == a fresh store (and the HTTP route) for the current state; returns it."""
    got = store.verify()
    assert got == uncached_verify(store)
    assert got == LedgerStore(path).verify()
    return got


# ---- I1/I2: the key's own parts: live segment bytes (open and closed) --------------------------------------


def test_i1_same_size_edit_of_the_open_segment_is_seen(tmp_path):
    s, p, _ = three_segments(tmp_path)
    warm(s)
    raw = p.read_bytes()
    i = raw.index(b'"tag"')
    p.write_bytes(raw[:i] + raw[i:].replace(b"open", b"opeX", 1))   # same length
    assert len(p.read_bytes()) == len(raw)
    got = agrees(s, p)
    assert got.ok is False and "hash mismatch" in (got.reason or "")


def test_i2_same_size_edit_of_a_closed_live_segment_is_seen(tmp_path):
    s, p, _ = three_segments(tmp_path)
    warm(s)
    closed = p.parent / next(e["file"] for e in journal_records(p) if e.get("op") == "rotate-intent")
    raw = closed.read_bytes()
    i = raw.index(b'"tag"')
    closed.write_bytes(raw[:i] + raw[i:].replace(b"seg1", b"segX", 1))
    got = agrees(s, p)
    assert got.ok is False and got.break_segment == 1


# ---- I3: existence of a live segment file (raw None vs bytes) -----------------------------------------------


def test_i3_a_deleted_then_restored_closed_segment_is_seen_both_ways(tmp_path):
    s, p, _ = three_segments(tmp_path)
    warm(s)
    closed = p.parent / next(e["file"] for e in journal_records(p) if e.get("op") == "rotate-intent")
    data = closed.read_bytes()
    closed.unlink()
    got = agrees(s, p)
    assert got.ok is False and "is missing" in (got.reason or "")
    closed.write_bytes(data)                                         # back, byte for byte
    assert agrees(s, p).ok is True


# ---- I4: the journal's bytes (layout.journal.raw), incl. a torn tail and a bad line ---------------------


def test_i4a_a_torn_journal_tail_changes_the_key_and_not_the_verdict(tmp_path):
    s, p, _ = three_segments(tmp_path)
    before = warm(s)
    with open(journal_path_for(p), "ab") as fh:
        fh.write(b'{"op":"rotate-in')                                # no newline: a torn tail, ignored
    assert agrees(s, p) == before


def test_i4b_an_appended_invalid_journal_line_is_seen(tmp_path):
    s, p, _ = three_segments(tmp_path)
    warm(s)
    with open(journal_path_for(p), "ab") as fh:
        fh.write(b'{"op":"nope"}\n')
    got = agrees(s, p)
    assert got.ok is False and "journal line" in (got.reason or "")


def test_i4c_an_appended_archive_op_drops_the_oldest_segment_from_the_walk_and_is_seen(tmp_path):
    """The journal 'archive' op is not tamper-evident by itself (store.py _verify_archived docstring): appended
    to the journal with the segment file left in place it must be answered from the evidence, not the cache."""
    s, p, _ = three_segments(tmp_path)
    warm(s)
    rec = next(r for r in journal_records(p) if r.get("op") == "rotate-commit")
    entry = next(r for r in journal_records(p) if r.get("op") == "rotate-intent")
    with open(journal_path_for(p), "ab") as fh:
        fh.write(store_mod.journal_line({
            "op": "archive", "n": entry["n"], "file": entry["file"],
            "archived_to": str(tmp_path / "nowhere" / entry["file"]),
            "sidecar": str(tmp_path / "nowhere" / (entry["file"] + ".segment.json")),
            "sha256": "0" * 64, "at": rec["closed_at"], "operator": "attacker",
        }))
    got = agrees(s, p)
    assert got.ok is False


# ---- I5..I7: archived ledgers: files OUTSIDE the key (T8 bypasses the cache) --------------------------------


@pytest.fixture
def archived(tmp_path):
    s, p, _ = three_segments(tmp_path)
    arch = tmp_path / "archive"
    entry = archive_oldest_for_test(s, arch)
    warm(s)
    return s, p, arch / entry["file"], entry


def test_i5_archive_copy_bytes_and_i6_existence_are_read_every_time(archived):
    s, p, copy, _ = archived
    data = copy.read_bytes()
    copy.write_bytes(data.replace(b"seg1", b"segX", 1))
    assert agrees(s, p).ok is False
    copy.write_bytes(data)
    assert agrees(s, p).ok is True                       # restored: the verdict follows the file back
    copy.unlink()
    assert agrees(s, p).ok is False
    copy.write_bytes(data)
    assert agrees(s, p).ok is True


def test_i7_a_pending_move_file_in_the_ledger_dir_is_read_every_time(tmp_path):
    """Journal 'archive' op written, file not yet moved: the file in the ledger directory is the evidence."""
    s, p, _ = three_segments(tmp_path)
    arch = tmp_path / "archive"
    arch.mkdir()
    with s._writer():
        s._ensure_fresh_locked()
        entry = next(e for e in store_mod.parse_journal(store_mod.read_shared(s.journal_path)).closed
                     if not e.get("archived_to"))
        src = p.parent / entry["file"]
        import hashlib
        s._journal_append_locked({
            "op": "archive", "n": entry["n"], "file": entry["file"],
            "archived_to": str(arch / entry["file"]), "sidecar": str(arch / (entry["file"] + ".segment.json")),
            "sha256": hashlib.sha256(src.read_bytes()).hexdigest(), "at": "2026-09-12T00:00:00+00:00",
            "operator": "test",
        })
        s._recover_locked()
    warm(s)
    data = src.read_bytes()
    src.write_bytes(data.replace(b"seg1", b"segX", 1))
    assert agrees(s, p).ok is False
    src.write_bytes(data)
    assert agrees(s, p).ok is True


def test_i8_a_retention_event_naming_the_digest_is_evidence_from_the_live_bytes_only(tmp_path):
    """When a hash-chained retention event names the archived segment WITH its sha-256, the archive copy is not
    consulted: its deletion cannot change the verdict (and is still equal to uncached / fresh)."""
    s, p, _ = three_segments(tmp_path)
    arch = tmp_path / "archive"
    entry = archive_oldest_for_test(s, arch)
    s.append("ledger.retention.applied", {"archive_evidence": [{"n": entry["n"],
                                                                 "sha256": next(r for r in journal_records(p)
                                                                                if r.get("op") == "archive")["sha256"]}]},
             agent_id="ledger")
    before = warm(s)
    (arch / entry["file"]).unlink()
    assert agrees(s, p) == before


# ---- I9: the clock ------------------------------------------------------------------------------------------


def test_i9_verify_never_reads_the_clock(tmp_path, monkeypatch):
    s, p, _ = three_segments(tmp_path)
    before = warm(s)

    class NoClock(real_datetime):
        @classmethod
        def now(cls, *a, **k):
            raise AssertionError("verify() read the wall clock")

        @classmethod
        def utcnow(cls):
            raise AssertionError("verify() read the wall clock")

    monkeypatch.setattr(store_mod, "datetime", NoClock)
    monkeypatch.setattr(store_mod.time, "time", lambda: (_ for _ in ()).throw(AssertionError("time.time")))
    assert s.verify() == before                      # cached path
    assert uncached_verify(s) == before              # and the uncached walk
    assert LedgerStore(p).verify() == before         # and a fresh store (journal parse + layout + walk)


# ---- I10: environment ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("name,value", [
    ("FIELD_LEDGER_READ_CONCURRENCY", "0"), ("FIELD_LEDGER_READ_CONCURRENCY", "8"),
    ("FIELD_DATA_DIR", "/nonexistent-dir-for-test"), ("FIELD_LEDGER_ARCHIVE_DIR", "/nonexistent-dir-for-test"),
    ("FIELD_LEDGER_REQUIRE_SIGNING", "1"), ("FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE", "1"),
    ("FIELD_LEDGER_SIGN_KEY", "/nonexistent/key.pem"), ("FIELD_LEDGER_CALLER_KEYRING", "/nonexistent/ring"),
])
def test_i10_the_environment_does_not_move_the_verdict(tmp_path, monkeypatch, name, value):
    s, p, _ = three_segments(tmp_path)
    before = warm(s)
    monkeypatch.setenv(name, value)
    assert s.verify() == before
    assert uncached_verify(s) == before
    assert LedgerStore(p).verify() == before


# ---- I11: signing keys, caller keyring, anchors: not read by verify() (served /verify is chain-only) --------


def test_i11a_signing_policy_and_caller_keyring_do_not_move_the_verdict(tmp_path):
    priv, _pub = generate_keypair()
    ring = tmp_path / "ring"
    ring.mkdir()
    s = LedgerStore(tmp_path / "events.jsonl", signing=SigningConfig(private_key_pem=priv))
    fill(s, 5)
    before = warm(s)
    other_priv, _ = generate_keypair()
    for cfg in (SigningConfig(), SigningConfig(private_key_pem=other_priv), SigningConfig(require_signing=True)):
        s.signing = cfg
        assert s.verify() == before
        assert uncached_verify(s) == before
        assert LedgerStore(s.path, signing=cfg).verify() == before
    (ring / "x.pub.pem").write_text("not a key")
    assert s.verify() == before


def test_i11b_a_flipped_signature_changes_the_bytes_and_chain_only_verify_stays_ok_by_design(tmp_path):
    """The signature is OUTSIDE the hash: flipping it changes the cache key (so verify recomputes) but a chain
    walk is still intact. Documented: served GET /verify is chain only (README 'Per-event signatures');
    `verify --event-pubkey` is what catches it, and it runs outside the cache."""
    priv, pub = generate_keypair()
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p, signing=SigningConfig(private_key_pem=priv))
    fill(s, 4)
    before = warm(s)
    lines = p.read_text().splitlines()
    rec = json.loads(lines[1])
    sig = rec["signature"]
    rec["signature"] = ("A" if sig[0] != "A" else "B") + sig[1:]
    lines[1] = json.dumps(rec)
    p.write_text("\n".join(lines) + "\n")
    assert agrees(s, p) == before                      # chain walk: same verdict, fresh and cached alike
    pub_file = tmp_path / "pub.pem"
    pub_file.write_text(pub)
    r = runner.invoke(cli_app, ["verify", "--path", str(p), "--event-pubkey", str(pub_file)])
    assert r.exit_code == 1 and "index 1" in r.output


def test_i11c_cli_event_pubkey_and_anchors_are_checked_outside_the_chain_cache(tmp_path):
    """Same ledger, same bytes, two CLI runs: the pubkey / anchor file decide, never a cached chain verdict."""
    priv, pub = generate_keypair()
    _, wrong_pub = generate_keypair()
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p, signing=SigningConfig(private_key_pem=priv))
    fill(s, 3)
    warm(s)
    good, bad = tmp_path / "good.pem", tmp_path / "bad.pem"
    good.write_text(pub)
    bad.write_text(wrong_pub)
    ok = runner.invoke(cli_app, ["verify", "--path", str(p), "--event-pubkey", str(good)])
    no = runner.invoke(cli_app, ["verify", "--path", str(p), "--event-pubkey", str(bad)])
    assert ok.exit_code == 0 and no.exit_code == 1
    # anchors: an anchor naming a head the chain does not hold fails; the chain bytes did not change
    anchors = tmp_path / "a.jsonl"
    anchors.write_text(json.dumps({"anchored_at": "2026-09-01T00:00:00+00:00", "chain_length": 3,
                                   "head_hash": "f" * 64}) + "\n")
    r = runner.invoke(cli_app, ["verify", "--path", str(p), "--anchors", str(anchors)])
    assert r.exit_code != 0 and "OK" not in r.output.splitlines()[-1]


# ---- I12: the HTTP route reads the same store: nothing extra -----------------------------------------------


def test_i12_get_verify_follows_the_bytes_after_a_warm_cache(tmp_path):
    s, p, _ = three_segments(tmp_path)
    client = TestClient(create_app(s))
    assert client.get("/verify").json()["ok"] is True
    assert client.get("/verify").json()["ok"] is True
    raw = p.read_bytes()
    i = raw.index(b'"tag"')
    p.write_bytes(raw[:i] + raw[i:].replace(b"open", b"opeX", 1))
    body = client.get("/verify").json()
    fresh = LedgerStore(p).verify()
    assert body["ok"] is False and body["first_break_index"] == fresh.first_break_index
    assert body["reason"] == fresh.reason


# ---- I13: caller mutation of what a read returned (the one input OUTSIDE the key that matters) -------------


def test_i13a_mutating_the_returned_verification_does_not_poison_the_cache(tmp_path):
    s, p, _ = three_segments(tmp_path)
    first = warm(s)
    got = s.verify()
    got.ok, got.reason, got.length = False, "poisoned", -1
    assert s.verify() == first


@pytest.mark.xfail(strict=True, reason="B-GL-verify-cache-key finding: the T7 parse cache hands out its own "
                   "LedgerEvent objects (and their payload dicts), so a caller that mutates an event returned by "
                   "events() makes the next verify() of the unchanged bytes report a tamper. No in-repo caller "
                   "mutates a returned event; a copy on read costs more than the parse it saves (measured), so "
                   "the fix is a design decision (read-only contract or immutable cached events), not made here.")
def test_i13b_mutating_a_returned_event_does_not_poison_a_later_verify(tmp_path):
    s = LedgerStore(tmp_path / "events.jsonl")
    fill(s, 5)
    warm(s)
    s.events()[0].payload["n"] = 999                  # a caller edits what events() returned
    s.append("t", {"more": 1}, agent_id="a")          # key changes: the next verify re-walks the cached parse
    assert s.verify().ok is True and s.verify() == LedgerStore(s.path).verify()


"""
INPUTS verify() reads (services/sealed-ledger/src/sealed_ledger/store.py, at 35c62fd4):

  LedgerStore.verify:2271 -> _take_snapshot(tolerant=True) -> _verified:1764 -> Snapshot.verify:1136
  key (live-only ledger): Layout (== SegView list, JournalState incl. the journal's raw bytes, error,
  archived) and every live segment's raw bytes (None = file absent).

  I1  open segment bytes                      in key            test_i1
  I2  closed live segment bytes               in key            test_i2
  I3  closed segment file existence           in key (raw None) test_i3
  I4  journal bytes (torn tail, bad line, an appended 'archive' op)   in key (layout.journal.raw)  test_i4a-c
  I5  archive copy bytes (archived_to)        NOT in key; cache bypassed once layout.archived (T8)   test_i5
  I6  archive copy existence                  same              test_i5
  I7  archived/pending-move file in ledger dir  same            test_i7
  I8  retention event naming the digest       in live bytes (key); copy not read when it names it  test_i8
  I9  clock                                   not read          test_i9
  I10 environment (read concurrency, data dir, archive dir, signing/caller env)  not read by verify   test_i10
  I11 signing key / caller keyring / anchors  not read: served /verify is chain only (README); the CLI's
      --event-pubkey/--caller-keyring/--anchors run AFTER the walk, outside the cache                  test_i11a-c
  I12 HTTP layer                              reads store.verify() only                                test_i12
  I13 in-memory aliasing of the parse cache   NOT covered: see test_i13b (xfail strict, a finding)
"""
