"""T8: the /verify result cache (T7, LedgerStore._verified) must never answer ok for a ledger whose archive
evidence has been damaged.

T7 keys the cached result on the layout and the live segments' bytes. But once any segment is ARCHIVED, the
verification (Snapshot._verify_archived) also reads files that are not in that key: the archived segment's file
in the ledger directory (a pending move) and its archive copy at ``archived_to``, whenever no retention event
names the segment with its sha-256. A byte flipped in, or the deletion of, the archive copy therefore left
/verify answering ok=True from the cache while a fresh store answers ok=False (T7 post-merge review, reproduced).

Every test compares the store's verify() with an UNCACHED verification of the very same read.
"""

from __future__ import annotations

import hashlib

import pytest

import sealed_ledger.store as store_mod
from sealed_ledger.store import LedgerStore, journal_path_for

from ledger_c2_support import archive_oldest_for_test, journal_records, three_segments


def uncached_verify(store: LedgerStore):
    """What verification says about the bytes and files as they are now, with no cache anywhere."""
    snap = store._take_snapshot(tolerant=True)
    return store_mod.Snapshot(snap.layout, snap.raw, 1, tolerant=True).verify()


@pytest.fixture
def archived(tmp_path):
    """Three segments, the oldest archived (journal op + file moved to ARCH), no retention event: so the
    archive copy is the evidence, as for a run killed before its event."""
    s, p, _ = three_segments(tmp_path)
    arch = tmp_path / "archive"
    entry = archive_oldest_for_test(s, arch)
    first = s.verify()
    assert first.ok, first.reason                  # the baseline is healthy ...
    assert s.verify() == first                     # ... and the second call is the cached one
    return s, p, arch / entry["file"]


def test_a_flipped_byte_in_the_archive_copy_is_seen_after_a_cached_verify(archived):
    s, p, copy = archived
    raw = copy.read_bytes()
    i = raw.index(b'"tag"')
    copy.write_bytes(raw[:i] + raw[i:].replace(b"seg1", b"segX", 1))
    want = uncached_verify(s)
    assert want.ok is False, "the damage must be detectable at all"
    assert s.verify() == want
    assert LedgerStore(p).verify() == want         # and a fresh store agrees


def test_a_deleted_archive_copy_is_seen_after_a_cached_verify(archived):
    s, p, copy = archived
    copy.unlink()
    want = uncached_verify(s)
    assert want.ok is False and "archive copy" in (want.reason or "")
    assert s.verify() == want
    assert LedgerStore(p).verify() == want


def test_an_intact_archived_ledger_still_verifies_and_stays_equal_to_uncached(archived):
    s, p, copy = archived
    for _ in range(3):
        assert s.verify() == uncached_verify(s)
    s.append("t1", {"more": True}, agent_id="a0")
    assert s.verify() == uncached_verify(s) and s.verify().ok


def test_an_edited_journal_head_hash_is_seen_after_a_cached_verify(tmp_path):
    """The key must include the journal state, not only the segment bytes: warm the cache, change a closed
    segment's head_hash in the journal (the segment files are untouched), verify must equal an uncached run."""
    s, p, _ = three_segments(tmp_path)
    warm = s.verify()
    assert warm.ok and s.verify() == warm
    journal = journal_path_for(p)
    raw = journal.read_bytes()
    marker = b'"head_hash":"'
    i = raw.index(marker) + len(marker)
    flipped = b"0" if raw[i:i + 1] != b"0" else b"1"
    journal.write_bytes(raw[:i] + flipped + raw[i + 1:])               # same length, one hex digit
    want = uncached_verify(s)
    assert want.ok is False, "the edit must be detectable at all"
    assert s.verify() == want


def test_the_newline_guard_on_extension_is_pinned_for_both_modes(tmp_path):
    """A cached parse of bytes with no trailing newline (a valid last record the reader accepts) must not be
    extended with more bytes: `{a}{b}` on one line is not valid JSON, and an uncached read raises on it."""
    s = LedgerStore(tmp_path / "events.jsonl")
    for i in range(3):
        s.append("t", {"n": i}, agent_id="a")
    lines = [x.rstrip(b"\r") for x in s.path.read_bytes().split(b"\n") if x.strip()]
    first, second = lines[0], lines[1]
    key = tmp_path / "other.jsonl"
    for tolerant in (False, True):
        store = LedgerStore(tmp_path / f"fresh-{tolerant}.jsonl")
        store._parsed(key, first, tolerant)                           # cached: a record, no newline
        whole = first + second + b"\n"                                # the same line grown, not terminated before
        if tolerant:
            assert store._parsed(key, whole, True) == store_mod._parse_events_located(whole)
        else:
            with pytest.raises(ValueError):
                store_mod._parse_events(whole)
            with pytest.raises(ValueError):
                store._parsed(key, whole, False)


def test_the_cached_verify_result_is_still_reused_when_nothing_is_archived(tmp_path):
    """The bypass is for archived ledgers only: a plain rotated ledger keeps the T7 reuse (a second verify
    validates no event)."""
    s, _, _ = three_segments(tmp_path)
    calls = [0]
    original = store_mod.Snapshot.verify

    def counting(self):
        calls[0] += 1
        return original(self)

    store_mod.Snapshot.verify = counting
    try:
        a = s.verify()
        b = s.verify()
    finally:
        store_mod.Snapshot.verify = original
    assert a == b and calls[0] == 1


def test_the_archive_copy_check_digest_helper_is_what_the_journal_recorded(archived):
    """Sanity for the fixture: the journal's sha256 of the archived segment is the archive copy's digest."""
    s, p, copy = archived
    rec = [r for r in journal_records(p) if r.get("op") == "archive"][0]
    assert rec["sha256"] == hashlib.sha256(copy.read_bytes()).hexdigest()
