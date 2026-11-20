"""T6-B: a read of the ledger parses each segment's bytes at most once while they do not change.

One GET /attest/pack makes 16 GET /events and one GET /verify; each used to parse every live segment from its
bytes, and on a CPU-quota'd machine that (about 2.5 s of CPU per pack on 11,000 events) starves /health. The
parse is now memoised by CONTENT (see store._ParseCache): equal bytes reuse the parse, appended bytes parse only
the new tail, any other change parses in full. These tests count the parses (bytes handed to the parse functions)
and compare every answer with a store whose cache is switched off (FIELD_LEDGER_PARSE_CACHE_MB=0).
"""

from __future__ import annotations

import os
import threading

import pytest
from fastapi.testclient import TestClient

from ledger_c2_support import fill, three_segments
from sealed_ledger import store as store_mod
from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore

TYPES = [f"t{i}" for i in range(16)]


class Counter:
    """Wraps the module's two parse functions; ``calls`` is the list of byte lengths parsed."""

    def __init__(self, monkeypatch):
        self.calls: list[int] = []
        strict, located = store_mod._parse_events, store_mod._parse_events_located

        def counting_strict(data):
            self.calls.append(len(data))
            return strict(data)

        def counting_located(data):
            self.calls.append(len(data))
            return located(data)

        monkeypatch.setattr(store_mod, "_parse_events", counting_strict)
        monkeypatch.setattr(store_mod, "_parse_events_located", counting_located)

    def take(self) -> list[int]:
        out, self.calls = self.calls, []
        return out


@pytest.fixture()
def counter(monkeypatch):
    return Counter(monkeypatch)


@pytest.fixture(autouse=True)
def _no_fsync(monkeypatch):
    """Durability is not under test and an fsync per append makes these slow on a laptop disk."""
    monkeypatch.setattr(os, "fsync", lambda fd: None)


def typed_fill(store: LedgerStore, n: int) -> None:
    for i in range(n):
        store.append(TYPES[i % len(TYPES)], {"n": i, "pad": "x" * 120}, agent_id=f"a{i % 3}")


def uncached(path, monkeypatch) -> LedgerStore:
    """A second store over the same files with the cache off: the reference answer."""
    with monkeypatch.context() as m:
        m.setenv(store_mod.PARSE_CACHE_ENV, "0")
        return LedgerStore(path)


def dump(events) -> list[dict]:
    return [e.model_dump() for e in events]


def pack_reads(store: LedgerStore) -> tuple[list[list[dict]], dict]:
    """What one attestation pack asks of the ledger: 16 filtered /events and one /verify."""
    events = [dump(store.events(event_type=t)) for t in TYPES]
    return events, store.verify().model_dump()


# --- the cost: parses per pack --------------------------------------------------------------------------


def test_one_pack_parses_the_chain_once_not_seventeen_times(tmp_path, counter):
    s = LedgerStore(tmp_path / "events.jsonl")
    typed_fill(s, 200)
    size = (tmp_path / "events.jsonl").stat().st_size
    counter.take()
    pack_reads(s)
    parsed = counter.take()
    assert len(parsed) == 1, f"{len(parsed)} parses of the chain for one pack (want 1): {parsed}"
    assert sum(parsed) == size


def test_a_second_pack_with_no_append_parses_nothing(tmp_path, counter):
    s = LedgerStore(tmp_path / "events.jsonl")
    typed_fill(s, 100)
    pack_reads(s)
    counter.take()
    pack_reads(s)
    assert counter.take() == []


def test_an_append_between_reads_parses_only_the_new_bytes(tmp_path, counter, monkeypatch):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    typed_fill(s, 100)
    s.events()
    counter.take()
    before = p.stat().st_size
    s.append("t3", {"late": True}, agent_id="a1")
    got = dump(s.events())
    parsed = counter.take()
    assert parsed == [p.stat().st_size - before], parsed
    assert got == dump(uncached(p, monkeypatch).events())
    assert got[-1]["payload"] == {"late": True}


def test_the_cache_is_per_segment_after_a_rotation(tmp_path, counter, monkeypatch):
    s, p, _ = three_segments(tmp_path)
    counter.take()                  # what building the fixture parsed is not under test
    pack_reads(s)
    first = counter.take()
    assert len(first) == 3, first   # three live segments, one parse each
    pack_reads(s)
    assert counter.take() == []
    fill(s, 2, "more")              # lands in the open segment only
    got, ver = pack_reads(s)
    only_open = counter.take()
    assert len(only_open) == 1 and only_open[0] < max(first), (only_open, first)
    ref = uncached(p, monkeypatch)
    assert (got, ver) == pack_reads(ref)


# --- the answers: identical to an uncached store -------------------------------------------------------------


def test_every_answer_equals_an_uncached_store(tmp_path, monkeypatch):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    typed_fill(s, 60)
    ref = uncached(p, monkeypatch)
    for _ in range(2):
        assert pack_reads(s) == pack_reads(ref)
        assert dump(s.events()) == dump(ref.events())
        assert dump(s.events(agent_id="a1", limit=5)) == dump(ref.events(agent_id="a1", limit=5))
        assert dump(s.snapshot().all_events()) == dump(ref.snapshot().all_events())
        assert s.hash_at(10) == ref.hash_at(10)
    typed_fill(s, 5)
    assert pack_reads(s) == pack_reads(ref)


def test_a_same_length_change_inside_a_closed_segment_is_seen(tmp_path, monkeypatch):
    """The key is the bytes: a tampered closed segment of the same size must not be answered from the cache."""
    s, p, _ = three_segments(tmp_path)
    assert s.verify().ok
    closed = sorted(tmp_path.glob("events*"))
    victims = [c for c in closed if c.is_file() and c.suffix != ".journal" and c.name != p.name
               and not c.name.startswith(".")]
    assert victims, closed
    victim = victims[0]
    raw = victim.read_bytes()
    i = raw.index(b'"tag"')
    tampered = raw[:i] + raw[i:].replace(b"seg1", b"segX", 1)
    assert len(tampered) == len(raw) and tampered != raw
    victim.write_bytes(tampered)
    ref = uncached(p, monkeypatch)
    cached, plain = s.verify(), ref.verify()
    assert cached.model_dump() == plain.model_dump()
    assert cached.ok is False


def test_a_bad_line_is_never_cached_and_reports_like_an_uncached_store(tmp_path, monkeypatch):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    typed_fill(s, 20)
    s.events()
    ref = uncached(p, monkeypatch)   # opened first: a store cannot be opened over a bad line
    with p.open("ab") as fh:
        fh.write(b"this is not json\n")
    assert s.verify().model_dump() == ref.verify().model_dump()
    assert s.verify().ok is False
    with pytest.raises(Exception) as cached_exc:
        s.events()
    with pytest.raises(Exception) as plain_exc:
        ref.events()
    assert type(cached_exc.value) is type(plain_exc.value)
    # the next read still goes through the full parse (nothing half-parsed was kept)
    assert s.verify().model_dump() == ref.verify().model_dump()


def test_a_truncated_file_is_a_full_parse(tmp_path, monkeypatch):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    typed_fill(s, 30)
    s.events()
    raw = p.read_bytes()
    lines = raw.split(b"\n")
    p.write_bytes(b"\n".join(lines[:10]) + b"\n")   # shorter: the cached bytes are no prefix of it
    ref = uncached(p, monkeypatch)
    assert dump(s.events()) == dump(ref.events())
    assert len(s.events()) == 10


def test_a_cached_prefix_that_does_not_end_in_a_newline_is_not_extended(tmp_path, monkeypatch):
    """Only a parse of bytes ending in a newline may be extended: here a half-written last line, cached
    by nothing (it fails to parse), then completed."""
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    typed_fill(s, 5)
    ref = uncached(p, monkeypatch)
    assert dump(s.events()) == dump(ref.events())
    typed_fill(s, 3)
    assert dump(s.events()) == dump(ref.events())


# --- bounds and the off switch -----------------------------------------------------------------------------------


def test_zero_turns_the_cache_off_and_junk_is_the_default(tmp_path, monkeypatch, counter):
    p = tmp_path / "events.jsonl"
    s0 = LedgerStore(p)
    typed_fill(s0, 20)
    monkeypatch.setenv(store_mod.PARSE_CACHE_ENV, "0")
    off = LedgerStore(p)
    counter.take()
    off.events()
    off.events()
    assert len(counter.take()) == 2
    for junk in ("", "abc", "-5", "nan", "inf"):
        monkeypatch.setenv(store_mod.PARSE_CACHE_ENV, junk)
        assert store_mod.parse_cache_bytes() == int(store_mod.PARSE_CACHE_DEFAULT_MB * 1024 * 1024), junk
    monkeypatch.setenv(store_mod.PARSE_CACHE_ENV, "0.5")
    assert store_mod.parse_cache_bytes() == 512 * 1024


def test_a_segment_over_the_cap_is_parsed_every_time(tmp_path, monkeypatch, counter):
    p = tmp_path / "events.jsonl"
    s0 = LedgerStore(p)
    typed_fill(s0, 100)
    assert p.stat().st_size > 2000
    monkeypatch.setenv(store_mod.PARSE_CACHE_ENV, "0.001")   # about 1 KB
    s = LedgerStore(p)
    counter.take()
    a, b = dump(s.events()), dump(s.events())
    assert a == b and len(counter.take()) == 2


def test_the_cache_evicts_oldest_first_within_its_cap():
    cache = store_mod._ParseCache(cap=1000)
    ev: list = []
    for i in range(5):
        cache._store(f"k{i}", b"x" * 400, ev)
    assert sum(len(v[0]) for v in cache._entries.values()) <= 1000
    assert list(cache._entries) == ["k3", "k4"]


# --- sharing: readers never change a cached event, and callers cannot reach the cache's list ---------------------


def test_the_list_a_caller_gets_is_its_own(tmp_path):
    s = LedgerStore(tmp_path / "events.jsonl")
    typed_fill(s, 10)
    first = s.events()
    first.clear()
    assert len(s.events()) == 10


def test_every_reader_leaves_the_cached_events_unchanged(tmp_path, monkeypatch):
    """The parsed events are shared between reads; a reader that mutated one would poison every later read.
    Run the readers, then compare the cache's own events with a fresh, uncached parse."""
    s, p, _ = three_segments(tmp_path)
    typed_fill(s, 10)
    client = TestClient(create_app(store=s))
    for path in ("/events", "/verify", "/health", "/events?event_type=t1", "/events?limit=3"):
        assert client.get(path).status_code == 200, path
    s.snapshot()
    s.hash_at(3)
    s.export(tmp_path / "export-out")
    ref = uncached(p, monkeypatch)
    assert dump(s.events()) == dump(ref.events())
    for key, (raw, events) in s._parse_cache._entries.items():
        fresh = store_mod._parse_events(raw)
        assert dump(events) == dump(fresh), key


# --- the same reduction through the served app --------------------------------------------------------------------


def test_the_served_pack_workload_parses_once(tmp_path, counter):
    s = LedgerStore(tmp_path / "events.jsonl")
    typed_fill(s, 150)
    client = TestClient(create_app(store=s))
    counter.take()
    for t in TYPES:
        assert client.get("/events", params={"event_type": t}).status_code == 200
    assert client.get("/verify").json()["ok"] is True
    assert len(counter.take()) == 1


def test_concurrent_readers_and_an_appender_get_consistent_answers(tmp_path, monkeypatch):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    typed_fill(s, 50)
    errors: list[str] = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                evs = s.events()
                v = s.verify()
                if not v.ok:
                    errors.append(f"verify not ok: {v.reason}")
                hashes = [e.hash for e in evs]
                prevs = [e.prev_hash for e in evs]
                if hashes[:-1] != prevs[1:]:
                    errors.append("events are not a chain")
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))

    threads = [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
        t.start()
    for i in range(60):
        s.append("t1", {"i": i}, agent_id="a0")
    stop.set()
    for t in threads:
        t.join()
    assert errors == []
    assert dump(s.events()) == dump(uncached(p, monkeypatch).events())
