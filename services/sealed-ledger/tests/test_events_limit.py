"""S3-11: GET /events `limit` keeps the NEWEST N matches (README: "the last N matches globally"), applied AFTER the
filters, in ascending order. Bounds ge=1, le=10000; out-of-range or non-integer is 422 and the input is never echoed.
Across a rotated ledger the cut is global, not per segment. Tests only."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from ledger_c2_support import fill, three_segments
from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore


@pytest.fixture()
def store(tmp_path):
    return LedgerStore(tmp_path / "events.jsonl")


@pytest.fixture()
def client(store):
    return TestClient(create_app(store=store))


def seeded(store, n=10):
    """n events, alternating agent a0/a1 and types t-even/t-odd; returns them in append order."""
    return [store.append("t-even" if i % 2 == 0 else "t-odd", {"n": i}, agent_id=f"a{i % 2}") for i in range(n)]


def hashes(resp):
    assert resp.status_code == 200, resp.text
    return [e["hash"] for e in resp.json()]


def test_limit_returns_the_newest_n_in_ascending_order_not_the_first_n(store, client):
    ev = seeded(store)
    assert hashes(client.get("/events", params={"limit": 3})) == [e.hash for e in ev[-3:]]
    assert hashes(client.get("/events", params={"limit": 3})) != [e.hash for e in ev[:3]]


def test_the_store_and_the_api_agree(store, client):
    ev = seeded(store)
    assert [e.hash for e in store.events(limit=4)] == hashes(client.get("/events", params={"limit": 4})) \
        == [e.hash for e in ev[-4:]]


def test_the_filter_applies_before_the_cut(store, client):
    ev = seeded(store)
    a0 = [e for e in ev if e.agent_id == "a0"]            # appended 0,2,4,6,8
    assert hashes(client.get("/events", params={"agent_id": "a0", "limit": 2})) == [e.hash for e in a0[-2:]]
    odd = [e for e in ev if e.event_type == "t-odd"]
    assert hashes(client.get("/events", params={"event_type": "t-odd", "limit": 2})) == [e.hash for e in odd[-2:]]
    # since is inclusive: from ev[4] on is 6 events, and the last 2 of those are the last 2 overall
    since = ev[4].ts
    assert hashes(client.get("/events", params={"since": since, "limit": 100})) == [e.hash for e in ev[4:]]
    assert hashes(client.get("/events", params={"until": ev[5].ts, "limit": 2})) == [e.hash for e in ev[4:6]]


def test_a_limit_larger_than_the_match_count_returns_all_matches(store, client):
    ev = seeded(store, 5)
    assert hashes(client.get("/events", params={"limit": 10_000})) == [e.hash for e in ev]
    assert hashes(client.get("/events", params={"agent_id": "nobody", "limit": 5})) == []


def test_no_limit_returns_everything(store, client):
    ev = seeded(store)
    assert hashes(client.get("/events")) == [e.hash for e in ev]


@pytest.mark.parametrize("limit", [1, 10_000])
def test_the_bounds_are_accepted(store, client, limit):
    ev = seeded(store, 3)
    assert hashes(client.get("/events", params={"limit": limit})) == [e.hash for e in ev][-limit:]


@pytest.mark.parametrize("limit", ["0", "-1", "10001", "abc", "1.5", "", "9" * 30])
def test_an_out_of_range_or_non_integer_limit_is_422(store, client, limit):
    seeded(store, 2)
    assert client.get("/events", params={"limit": limit}).status_code == 422


@pytest.mark.parametrize("limit", ["NOTANINT-ECHO-7731", "-98765432", "123456789"])
def test_a_rejected_limit_is_never_echoed_in_the_422_body(store, client, limit):
    r = client.get("/events", params={"limit": limit})
    assert r.status_code == 422, r.text
    assert limit not in r.text


def test_across_a_rotated_ledger_the_cut_is_global(tmp_path):
    s, _path, order = three_segments(tmp_path)              # 11 live events over 3 segments, rotation events included
    c = TestClient(create_app(store=s))
    assert hashes(c.get("/events")) == order
    assert hashes(c.get("/events", params={"limit": 6})) == order[-6:]      # spans the segment 2 / 3 boundary
    assert hashes(c.get("/events", params={"limit": 2})) == order[-2:]      # all inside the open segment
    assert hashes(c.get("/events", params={"limit": 11})) == order


def test_a_rotated_ledgers_filter_then_cut(tmp_path):
    s, _path, _order = three_segments(tmp_path)
    c = TestClient(create_app(store=s))
    actions = [e for e in s.events() if e.event_type == "action"]           # 4 + 3 + 2 = 9 across all segments
    assert len(actions) == 9
    got = hashes(c.get("/events", params={"event_type": "action", "limit": 4}))
    assert got == [e.hash for e in actions[-4:]]
