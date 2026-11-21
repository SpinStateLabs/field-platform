"""B-GL-events-limit-cheap: GET /events?limit=N (LedgerStore.events with a limit) reads the TAIL of the chain.

``events(limit=N)`` keeps the last N matches in global order. It used to parse every live segment to find them. It now
reads a window from the end of the open segment, parses its lines from the last one backwards, and stops at N matches;
when the window does not hold N matches it widens (x8) and, once the whole open segment is not enough, falls back to the
full read, so the answer is the same as the full read's.

One documented difference: a record that does not parse in a part of the chain the scan never reaches no longer makes
a limited read raise (events(limit=1) answers from the tail; the unlimited read and /verify still report it).
"""

from __future__ import annotations

import json
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


def test_limit_one_parses_a_handful_of_lines_not_the_chain(tmp_path, monkeypatch):
    s = fill(tmp_path / "events.jsonl", 600, pad=40)
    fresh = LedgerStore(s.path)
    want = raw_hashes(s.path)[-1:]
    c = Counter(monkeypatch)
    got = fresh.events(limit=1)
    parsed = c.n
    assert [e.hash for e in got] == want
    assert parsed <= 3, parsed                              # not 600


def test_a_small_limit_parses_about_that_many_lines(tmp_path, monkeypatch):
    s = fill(tmp_path / "events.jsonl", 600, pad=40)
    fresh = LedgerStore(s.path)
    c = Counter(monkeypatch)
    calls = []
    real = fresh._take_snapshot
    fresh._take_snapshot = lambda *a, **k: (calls.append(k.get("tail_bytes")), real(*a, **k))[1]
    got = fresh.events(limit=25)
    parsed = c.n
    assert len(got) == 25
    assert parsed <= 30, parsed
    assert len(calls) == 1 and calls[0] == LedgerStore.EVENTS_TAIL_WINDOW_BYTES, calls     # one window, no full read


@pytest.mark.parametrize("limit", [1, 2, 7, 50, 199, 200, 201, 5000])
def test_every_limit_equals_the_full_read_sliced(tmp_path, limit):
    s = fill(tmp_path / "events.jsonl", 200, pad=30)
    assert [e.hash for e in s.events(limit=limit)] == [e.hash for e in oracle(s, limit)]


@pytest.mark.parametrize("flt", [
    {"agent_id": "a1"}, {"event_type": "kill.agent"}, {"agent_id": "a2", "event_type": "action"},
    {"event_type": "does.not.exist"}, {"agent_id": "nobody"}])
@pytest.mark.parametrize("limit", [1, 5, 40, 500])
def test_filters_with_a_limit_equal_the_full_read_sliced(tmp_path, flt, limit):
    s = fill(tmp_path / "events.jsonl", 300, pad=30)
    assert [e.hash for e in s.events(limit=limit, **flt)] == [e.hash for e in oracle(s, limit, **flt)]


def test_time_bounds_with_a_limit(tmp_path):
    s = fill(tmp_path / "events.jsonl", 120, pad=10)
    mid = s.events()[60].ts
    for flt in ({"since": mid}, {"until": mid}, {"since": mid, "until": mid}):
        assert [e.hash for e in s.events(limit=9, **flt)] == [e.hash for e in oracle(s, 9, **flt)]


def test_a_match_that_is_only_at_the_start_of_the_chain_is_found_by_widening(tmp_path, monkeypatch):
    monkeypatch.setattr(LedgerStore, "EVENTS_TAIL_WINDOW_BYTES", 2048)
    s = LedgerStore(tmp_path / "events.jsonl")
    s.append("rare.type", {"first": True}, agent_id="r")
    for i in range(400):
        s.append("action", {"i": i, "pad": "y" * 60}, agent_id="a")
    got = LedgerStore(s.path).events(event_type="rare.type", limit=1)
    assert [e.event_type for e in got] == ["rare.type"]


def test_a_limit_larger_than_the_open_segment_crosses_into_the_closed_segments(tmp_path, monkeypatch):
    monkeypatch.setattr(LedgerStore, "EVENTS_TAIL_WINDOW_BYTES", 512)
    s, p, hashes = three_segments(tmp_path / "ledger")
    fresh = LedgerStore(p)
    full = [e.hash for e in fresh.events()]
    for limit in (1, 3, 5, len(full), len(full) + 10):
        assert [e.hash for e in fresh.events(limit=limit)] == full[-limit:]


def test_the_window_widens_when_the_first_window_holds_too_few_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(LedgerStore, "EVENTS_TAIL_WINDOW_BYTES", 1024)
    s = fill(tmp_path / "events.jsonl", 300, pad=80)
    fresh = LedgerStore(s.path)
    want = raw_hashes(s.path)[-120:]
    calls = []
    real = fresh._take_snapshot
    fresh._take_snapshot = lambda *a, **k: (calls.append(k.get("tail_bytes")), real(*a, **k))[1]
    got = fresh.events(limit=120)
    assert [e.hash for e in got] == want
    # widened 1024 -> 8192 -> 65536 and answered from the open segment: no full read (tail_bytes None) was taken
    assert calls and all(c is not None for c in calls) and calls == sorted(calls) and len(calls) >= 2, calls


def test_the_first_partial_line_of_a_window_is_never_parsed(tmp_path, monkeypatch):
    """The window starts mid-line; the cut line must be dropped, not parsed (it would raise)."""
    monkeypatch.setattr(LedgerStore, "EVENTS_TAIL_WINDOW_BYTES", 700)
    s = fill(tmp_path / "events.jsonl", 80, pad=50)
    for limit in (1, 2, 3, 4):
        assert [e.hash for e in LedgerStore(s.path).events(limit=limit)] == [e.hash for e in s.events()][-limit:]


def test_crlf_and_blank_lines_read_like_the_full_read(tmp_path):
    s = fill(tmp_path / "events.jsonl", 40, pad=20)
    raw = s.path.read_bytes()
    s.path.write_bytes(raw.replace(b"\n", b"\r\n\r\n"))
    fresh = LedgerStore(s.path)
    assert [e.hash for e in fresh.events(limit=7)] == [e.hash for e in fresh.events()][-7:]


def test_an_empty_ledger_and_a_missing_file(tmp_path):
    assert LedgerStore(tmp_path / "events.jsonl").events(limit=3) == []
    p = tmp_path / "x" / "events.jsonl"
    assert LedgerStore(p).events(limit=1) == []


def test_limit_validation_is_unchanged(tmp_path):
    s = fill(tmp_path / "events.jsonl", 3)
    for bad in (0, -1):
        with pytest.raises(ValueError):
            s.events(limit=bad)


def test_a_bad_time_bound_still_raises_before_reading(tmp_path):
    s = fill(tmp_path / "events.jsonl", 3)
    with pytest.raises(store_mod.InvalidTimeBound):
        s.events(limit=1, since="not a time")


def test_a_bad_line_inside_the_scanned_window_still_raises(tmp_path):
    s = fill(tmp_path / "events.jsonl", 20, pad=10)
    with open(s.path, "ab") as fh:
        fh.write(b"this is not json\n")
    with pytest.raises(ValueError):
        LedgerStore(s.path).events(limit=1)


def test_a_bad_line_the_scan_never_reaches_does_not_stop_a_limited_read_but_stops_the_full_read(tmp_path):
    """The documented difference: the tail answers from the tail; the unlimited read and /verify still see the break."""
    s = fill(tmp_path / "events.jsonl", 200, pad=40)
    lines = s.path.read_bytes().split(b"\n")
    lines[3] = b"{ broken"
    s.path.write_bytes(b"\n".join(lines))
    assert len(s.events(limit=2)) == 2                      # s was opened before the damage: a new store would refuse at open
    with pytest.raises(ValueError):
        s.events()
    assert s.verify().ok is False


def test_reads_stay_consistent_while_appends_and_a_rotation_happen(tmp_path):
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
        reader = LedgerStore(s.path)
        while time.monotonic() < deadline:
            got = reader.events(limit=10)
            for a, b in zip(got, got[1:]):
                if b.prev_hash != a.hash:
                    errors.append(("chain break inside a tail read", a.hash[:8], b.prev_hash[:8]))
    finally:
        stop.set()
        t.join(10)
    assert errors == []


def test_the_served_route_returns_the_same_body_as_the_full_read(tmp_path):
    from fastapi.testclient import TestClient
    from sealed_ledger.api import create_app

    s = fill(tmp_path / "events.jsonl", 90, pad=15)
    client = TestClient(create_app(store=s))
    served = client.get("/events", params={"limit": 4}).json()
    assert [e["hash"] for e in served] == [e.hash for e in s.events()][-4:]
    served = client.get("/events", params={"limit": 3, "event_type": "kill.agent"}).json()
    assert [e["hash"] for e in served] == [e.hash for e in s.events(event_type="kill.agent")][-3:]
