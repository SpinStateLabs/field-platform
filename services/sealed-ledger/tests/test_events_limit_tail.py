"""B-GL-events-limit-cheap: GET /events?limit=N (LedgerStore.events with a limit) does not walk the whole chain.

``events(limit=N)`` keeps the last N matches in global order. Two ways to find them without the full read's work:

* WARM (the T7 parse cache holds the open segment: every ledger whose live bytes fit PARSE_CACHE_MAX_BYTES, from the
  moment its store is opened): the cached parse is extended by the appended bytes (no line is parsed twice) and scanned
  from the newest event backwards, stopping at N matches.
* COLD (a ledger larger than the cache): ONE window from the end of the open segment is parsed from its last line
  backwards. Not widened: with fewer than N matches in the window the full read runs.

Every differential test runs in both modes. A store opened normally is warm (opening parses the chain into the cache);
``cold()`` empties the cache so the window path runs.
"""

from __future__ import annotations

import threading
import time

import pytest

import sealed_ledger.store as store_mod
from sealed_ledger.store import LedgerStore

from ledger_c2_support import three_segments


def fill(path, n, agents=3, types=("action", "kill.agent", "conformance.allow"), pad=0):
    s = LedgerStore(path)
    for i in range(n):
        s.append(types[i % len(types)], {"i": i, "pad": "x" * pad}, agent_id=f"a{i % agents}")
    return s


def cold(store):
    store._parse_cache.clear()
    return store


def open_store(path, mode):
    store = LedgerStore(path)
    return cold(store) if mode == "cold" else store


@pytest.fixture(params=["warm", "cold"])
def mode(request):
    return request.param


class Counter:
    """Counts LedgerEvent.model_validate calls (one per parsed line)."""

    def __init__(self, monkeypatch):
        self.n = 0
        real = store_mod.LedgerEvent.model_validate.__func__

        def counting(cls, *a, **k):
            self.n += 1
            return real(cls, *a, **k)

        monkeypatch.setattr(store_mod.LedgerEvent, "model_validate", classmethod(counting))


def raw_hashes(path):
    """Every event hash in file order, parsed without the store (and so without its parse cache)."""
    return [e.hash for e in store_mod._parse_events(path.read_bytes())]


def oracle(store, limit, **flt):
    """The full read, sliced: what events(limit=N) must equal."""
    return store.events(**flt)[-limit:]


def snapshot_calls(store):
    calls = []
    real = store._take_snapshot
    store._take_snapshot = lambda *a, **k: (calls.append(k.get("tail_bytes", "full")), real(*a, **k))[1]
    return calls


# ------------------------------------------------------------------------------------------ cost pins

def test_cold_limit_one_parses_a_handful_of_lines_not_the_chain(tmp_path, monkeypatch):
    s = fill(tmp_path / "events.jsonl", 600, pad=40)
    want = raw_hashes(s.path)[-1:]
    fresh = open_store(s.path, "cold")
    c = Counter(monkeypatch)
    got = fresh.events(limit=1)
    parsed = c.n
    assert [e.hash for e in got] == want
    assert parsed <= 3, parsed                              # not 600


def test_cold_small_limit_parses_about_that_many_lines_in_one_window(tmp_path, monkeypatch):
    s = fill(tmp_path / "events.jsonl", 600, pad=40)
    fresh = open_store(s.path, "cold")
    calls = snapshot_calls(fresh)
    c = Counter(monkeypatch)
    got = fresh.events(limit=25)
    parsed = c.n
    assert len(got) == 25
    assert parsed <= 30, parsed
    assert calls == [LedgerStore.EVENTS_TAIL_WINDOW_BYTES], calls     # one window, no full read


def test_warm_reads_parse_nothing_at_all(tmp_path, monkeypatch):
    """The cached parse is scanned from the newest event back: a limited read of a warm store parses no line, whatever
    the limit and the filter (review B-1: the pack's 16 reads must not parse a line twice)."""
    s = fill(tmp_path / "events.jsonl", 300, pad=20)
    fresh = LedgerStore(s.path)                                          # opening warms the cache
    c = Counter(monkeypatch)
    for kw in ({"limit": 1}, {"limit": 25}, {"limit": 10**6}, {"limit": 3, "event_type": "kill.agent"},
               {"limit": 5, "agent_id": "a1"}, {"limit": 2, "event_type": "no.such.type"}, {}):
        fresh.events(**kw)
    assert c.n == 0, c.n


def test_warm_reads_parse_each_appended_line_once_and_never_redo_the_cache(tmp_path, monkeypatch):
    """After an append the cached parse is extended by exactly the new line: 4 appends cost 4 parses however many
    limited reads follow each of them."""
    fill(tmp_path / "events.jsonl", 100, pad=20)
    s = LedgerStore(tmp_path / "events.jsonl")                          # opening warms the cache
    assert s.path in s._parse_cache
    c = Counter(monkeypatch)
    for k in range(4):
        s.append("action", {"k": k}, agent_id="w")
        s.events(limit=3)
        s.events(limit=1, event_type="action")
        s.events(limit=10**6)
    assert c.n <= 4, c.n


def test_a_warm_rare_filter_does_no_more_work_than_the_full_read(tmp_path, monkeypatch):
    """Review B-2: rare filter and a huge limit were 11-20x slower than the full read on a warm store."""
    s = fill(tmp_path / "events.jsonl", 400, pad=20)
    fresh = LedgerStore(s.path)
    matches_calls = {"tail": 0, "full": 0}
    real = store_mod.EventFilter.matches

    def counting(self, index, event):
        matches_calls["tail" if index == -1 else "full"] += 1
        return real(self, index, event)

    monkeypatch.setattr(store_mod.EventFilter, "matches", counting)
    fresh.events(agent_id="nobody", limit=50)
    fresh.events(limit=10**9)
    fresh.events(agent_id="nobody")
    # each limited read scans each event at most once; the full read's filter pass does the same
    assert matches_calls["tail"] <= 2 * 400 and matches_calls["full"] <= 400 + 1, matches_calls


# ------------------------------------------------------------------------------------ equivalence

@pytest.mark.parametrize("limit", [1, 2, 7, 50, 199, 200, 201, 5000])
def test_every_limit_equals_the_full_read_sliced(tmp_path, mode, limit):
    s = fill(tmp_path / "events.jsonl", 200, pad=30)
    fresh = open_store(s.path, mode)
    assert [e.hash for e in fresh.events(limit=limit)] == raw_hashes(s.path)[-limit:]


@pytest.mark.parametrize("flt", [
    {"agent_id": "a1"}, {"event_type": "kill.agent"}, {"agent_id": "a2", "event_type": "action"},
    {"event_type": "does.not.exist"}, {"agent_id": "nobody"}])
@pytest.mark.parametrize("limit", [1, 5, 40, 500])
def test_filters_with_a_limit_equal_the_full_read_sliced(tmp_path, mode, flt, limit):
    s = fill(tmp_path / "events.jsonl", 300, pad=30)
    fresh = open_store(s.path, mode)
    assert [e.hash for e in fresh.events(limit=limit, **flt)] == [e.hash for e in oracle(s, limit, **flt)]


def test_time_bounds_with_a_limit(tmp_path, mode):
    s = fill(tmp_path / "events.jsonl", 120, pad=10)
    mid = s.events()[60].ts
    fresh = open_store(s.path, mode)
    for flt in ({"since": mid}, {"until": mid}, {"since": mid, "until": mid}):
        assert [e.hash for e in fresh.events(limit=9, **flt)] == [e.hash for e in oracle(s, 9, **flt)]


def test_cold_with_too_few_matches_in_the_one_window_falls_back_to_the_full_read(tmp_path, monkeypatch):
    monkeypatch.setattr(LedgerStore, "EVENTS_TAIL_WINDOW_BYTES", 2048)
    s = LedgerStore(tmp_path / "events.jsonl")
    s.append("rare.type", {"first": True}, agent_id="r")
    for i in range(400):
        s.append("action", {"i": i, "pad": "y" * 60}, agent_id="a")
    fresh = open_store(s.path, "cold")
    calls = snapshot_calls(fresh)
    got = fresh.events(event_type="rare.type", limit=1)
    assert [e.event_type for e in got] == ["rare.type"]
    assert calls == [2048, "full"], calls              # ONE window (not widened), then the full read


def test_a_limit_larger_than_the_open_segment_crosses_into_the_closed_segments(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(LedgerStore, "EVENTS_TAIL_WINDOW_BYTES", 512)
    s, p, hashes = three_segments(tmp_path / "ledger")
    fresh = open_store(p, mode)
    full = [e.hash for e in LedgerStore(p).events()]
    for limit in (1, 3, 5, len(full), len(full) + 10):
        assert [e.hash for e in fresh.events(limit=limit)] == full[-limit:]


def test_the_first_partial_line_of_a_window_is_never_parsed(tmp_path, monkeypatch):
    """The window starts mid-line; the cut line must be dropped, not parsed (it would raise)."""
    monkeypatch.setattr(LedgerStore, "EVENTS_TAIL_WINDOW_BYTES", 700)
    s = fill(tmp_path / "events.jsonl", 80, pad=50)
    want = raw_hashes(s.path)
    for limit in (1, 2, 3, 4):
        assert [e.hash for e in open_store(s.path, "cold").events(limit=limit)] == want[-limit:]


@pytest.mark.parametrize("window", list(range(380, 460, 7)) + [1, 2, 3, 100])
def test_every_cold_window_size_returns_the_full_reads_answer(tmp_path, monkeypatch, window):
    """The window start can land anywhere, including right after a newline (that complete line is dropped; the single
    window then holds fewer matches and the full read answers)."""
    monkeypatch.setattr(LedgerStore, "EVENTS_TAIL_WINDOW_BYTES", window)
    s = fill(tmp_path / "events.jsonl", 30, pad=10)
    want = raw_hashes(s.path)
    for limit in (1, 2, 3, 29, 30, 31):
        assert [e.hash for e in open_store(s.path, "cold").events(limit=limit)] == want[-limit:]


def test_a_line_longer_than_the_window_falls_back_and_answers(tmp_path, monkeypatch):
    monkeypatch.setattr(LedgerStore, "EVENTS_TAIL_WINDOW_BYTES", 64)
    s = fill(tmp_path / "events.jsonl", 5, pad=3000)
    assert [e.hash for e in open_store(s.path, "cold").events(limit=2)] == raw_hashes(s.path)[-2:]


def test_crlf_and_blank_lines_read_like_the_full_read(tmp_path, mode):
    s = fill(tmp_path / "events.jsonl", 40, pad=20)
    raw = s.path.read_bytes()
    s.path.write_bytes(raw.replace(b"\n", b"\r\n\r\n"))
    fresh = open_store(s.path, mode)
    assert [e.hash for e in fresh.events(limit=7)] == [e.hash for e in fresh.events()][-7:]


def test_a_single_segment_ledger_with_fewer_matches_than_the_limit_is_answered_without_a_full_read(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(LedgerStore, "EVENTS_TAIL_WINDOW_BYTES", 10**9)
    s = fill(tmp_path / "events.jsonl", 200, pad=40)
    fresh = open_store(s.path, mode)
    calls = snapshot_calls(fresh)
    assert [e.hash for e in fresh.events(limit=10_000)] == raw_hashes(s.path)
    assert fresh.events(event_type="no.such.type", limit=3) == []
    assert "full" not in calls, calls


def test_an_empty_ledger_and_a_missing_file(tmp_path, mode):
    assert open_store(tmp_path / "events.jsonl", mode).events(limit=3) == []
    p = tmp_path / "x" / "events.jsonl"
    assert open_store(p, mode).events(limit=1) == []


def test_limit_validation_is_unchanged(tmp_path):
    s = fill(tmp_path / "events.jsonl", 3)
    for bad in (0, -1):
        with pytest.raises(ValueError):
            s.events(limit=bad)


def test_a_bad_time_bound_still_raises_before_reading(tmp_path):
    s = fill(tmp_path / "events.jsonl", 3)
    with pytest.raises(store_mod.InvalidTimeBound):
        s.events(limit=1, since="not a time")


# ------------------------------------------------------------------------- bad records, the gate

@pytest.mark.parametrize("bad", [b"this is not json", b'{"valid": "json", "but": "not an event"}'])
def test_a_bad_record_inside_the_scanned_part_raises_in_both_modes(tmp_path, mode, bad):
    s = fill(tmp_path / "events.jsonl", 40, pad=10)
    lines = s.path.read_bytes().split(b"\n")
    lines.insert(len(lines) - 5, bad)                       # five good lines after it, limit 10 reaches it
    s.path.write_bytes(b"\n".join(lines))
    store = s if mode == "warm" else cold(s)                # (a new store would refuse at open)
    with pytest.raises(ValueError):
        store.events(limit=10)


def test_a_bad_record_the_cold_scan_never_reaches_does_not_stop_a_limited_read(tmp_path):
    """The documented cold-only difference: the window answers from the tail; the unlimited read and /verify still
    see the break. (A warm read re-parses changed bytes in full, so it raises exactly like the full read.)"""
    s = fill(tmp_path / "events.jsonl", 200, pad=40)
    lines = s.path.read_bytes().split(b"\n")
    lines[3] = b"{ broken"
    s.path.write_bytes(b"\n".join(lines))
    cold(s)
    assert len(s.events(limit=2)) == 2
    with pytest.raises(ValueError):
        s.events()
    assert s.verify().ok is False
    warm_store = fill(tmp_path / "w" / "events.jsonl", 200, pad=40)
    warm_store.events()                                                  # a full read fills the cache
    assert warm_store.path in warm_store._parse_cache
    lines = warm_store.path.read_bytes().split(b"\n")
    lines[3] = b"{ broken"
    warm_store.path.write_bytes(b"\n".join(lines))
    with pytest.raises(ValueError):
        warm_store.events(limit=2)


@pytest.mark.parametrize("which", ["warm", "cold"])
def test_a_limited_read_waits_for_the_read_gate(tmp_path, which):
    """Review mutant 19: the tail snapshot is taken under the same read gate as every other whole-file read."""
    s = fill(tmp_path / "events.jsonl", 30, pad=10)
    store = open_store(s.path, which)
    held, release = threading.Event(), threading.Event()

    def hold():
        with store._gate():
            held.set()
            release.wait(30)

    holder = threading.Thread(target=hold, daemon=True)
    holder.start()
    assert held.wait(10)
    done: list = []
    reader = threading.Thread(target=lambda: done.append(store.events(limit=1)), daemon=True)
    reader.start()
    time.sleep(1.0)
    still_waiting = not done
    release.set()
    reader.join(30)
    holder.join(10)
    assert still_waiting, "a limited read answered while another reader held the gate"
    assert len(done) == 1 and len(done[0]) == 1


def test_reads_stay_consistent_while_appends_happen(tmp_path, mode):
    s = fill(tmp_path / "events.jsonl", 50, pad=20)
    stop = threading.Event()
    errors: list = []

    def appender():
        k = 0
        while not stop.is_set():
            s.append("action", {"k": k}, agent_id="w")
            k += 1
            time.sleep(0.001)

    t = threading.Thread(target=appender, daemon=True)
    t.start()
    try:
        deadline = time.monotonic() + 3.0
        reader = open_store(s.path, mode)
        while time.monotonic() < deadline:
            got = reader.events(limit=10)
            for a, b in zip(got, got[1:]):
                if b.prev_hash != a.hash:
                    errors.append(("chain break inside a tail read", a.hash[:8], b.prev_hash[:8]))
    finally:
        stop.set()
        t.join(10)
    assert errors == []


def test_the_served_route_returns_the_same_body_as_the_full_read(tmp_path, mode):
    from fastapi.testclient import TestClient
    from sealed_ledger.api import create_app

    s = fill(tmp_path / "events.jsonl", 90, pad=15)
    client = TestClient(create_app(store=open_store(s.path, mode)))
    served = client.get("/events", params={"limit": 4}).json()
    assert [e["hash"] for e in served] == raw_hashes(s.path)[-4:]
    served = client.get("/events", params={"limit": 3, "event_type": "kill.agent"}).json()
    assert [e["hash"] for e in served] == [e.hash for e in s.events(event_type="kill.agent")][-3:]
