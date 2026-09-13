"""C1: since/until compare instants (datetime.fromisoformat), inclusive.

Regression for the lexical string compare: with stored ts written as
``+00:00`` (make_event's default), a ``Z`` bound, a different offset, or
fractional seconds produced wrong windows. Every test here fails if
``EventFilter.matches`` goes back to comparing ``event.ts`` as a string.
"""

import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from field_core.ledger import GENESIS_HASH, make_event
from sealed_ledger.api import create_app
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import InvalidTimeBound, LedgerStore

# index: ts (instant)
TS = [
    "2026-09-12T10:00:00+00:00",          # 0: 10:00:00Z
    "2026-09-12T10:00:00.123456+00:00",   # 1: 10:00:00.123456Z
    "2026-09-12T06:00:00-05:00",          # 2: 11:00:00Z
    "2026-09-12T12:00:00+00:00",          # 3: 12:00:00Z
]


@pytest.fixture()
def fixed_store(tmp_path):
    """A valid chain whose timestamps mix offsets and fractional seconds."""
    path = tmp_path / "events.jsonl"
    prev, lines = GENESIS_HASH, []
    for i, ts in enumerate(TS):
        ev = make_event("action", {"i": i}, prev_hash=prev, agent_id="a1", ts=ts,
                        event_id=f"e-{i}")
        lines.append(ev.model_dump_json())
        prev = ev.hash
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    store = LedgerStore(path)
    assert store.verify().ok
    return store


def _idx(events):
    return [e.payload["i"] for e in events]


def test_z_bound_includes_events_in_that_second(fixed_store):
    # lexical: '...10:00:00+00:00' < '...10:00:00Z' and '...10:00:00.123456+00:00' < '...Z'
    assert _idx(fixed_store.events(since="2026-09-12T10:00:00Z")) == [0, 1, 2, 3]


def test_until_compares_instants_across_offsets(fixed_store):
    # lexical would include index 2 ('...T06:00:00-05:00' sorts before '...T10')
    assert _idx(fixed_store.events(until="2026-09-12T10:00:00+00:00")) == [0]
    assert _idx(fixed_store.events(until="2026-09-12T10:30:00Z")) == [0, 1]


def test_since_compares_instants_across_offsets(fixed_store):
    # lexical would drop index 2 (11:00Z written as 06:00-05:00)
    assert _idx(fixed_store.events(since="2026-09-12T10:30:00+00:00")) == [2, 3]


def test_bounds_are_inclusive_at_the_exact_instant(fixed_store):
    # the same instant written with a different offset on both bounds
    only_2 = fixed_store.events(since="2026-09-12T11:00:00Z", until="2026-09-12T07:00:00-04:00")
    assert _idx(only_2) == [2]
    only_1 = fixed_store.events(
        since="2026-09-12T10:00:00.123456Z", until="2026-09-12T10:00:00.123456+00:00"
    )
    assert _idx(only_1) == [1]
    assert _idx(fixed_store.events(since=TS[3], until=TS[3])) == [3]


def test_naive_and_date_only_bounds_are_utc(fixed_store):
    assert _idx(fixed_store.events(until="2026-09-12T10:00:00")) == [0]
    assert _idx(fixed_store.events(since="2026-09-12")) == [0, 1, 2, 3]
    # a date alone is 00:00:00 UTC that day — as an upper bound it excludes the day
    assert fixed_store.events(until="2026-09-12") == []
    assert _idx(fixed_store.events(until="2026-09-13")) == [0, 1, 2, 3]


def test_filters_combine_with_agent_and_type_and_limit(fixed_store):
    assert _idx(fixed_store.events(agent_id="a1", since="2026-09-12T10:00:00Z", limit=2)) == [2, 3]
    assert fixed_store.events(agent_id="other", since="2026-09-12T10:00:00Z") == []
    assert fixed_store.events(event_type="block", until="2026-09-13") == []


def test_unparseable_bound_is_refused_not_silently_empty(fixed_store, tmp_path):
    with pytest.raises(InvalidTimeBound, match="since"):
        fixed_store.events(since="garbage")
    with pytest.raises(InvalidTimeBound, match="until"):
        fixed_store.events(until="2026-13-45")
    with pytest.raises(InvalidTimeBound):
        fixed_store.export(tmp_path / "exports", since="yesterday")
    assert not (tmp_path / "exports").exists()


def test_api_events_filters_by_instant_and_422s_on_garbage(fixed_store):
    client = TestClient(create_app(store=fixed_store))
    r = client.get("/events", params={"since": "2026-09-12T10:00:00Z",
                                      "until": "2026-09-12T11:00:00Z"})
    assert r.status_code == 200
    assert [e["payload"]["i"] for e in r.json()] == [0, 1, 2]
    bad = client.get("/events", params={"until": "not-a-time"})
    assert bad.status_code == 422
    assert "until" in bad.json()["detail"]


def test_export_window_selects_the_same_events_as_events(fixed_store, tmp_path):
    client = TestClient(create_app(store=fixed_store))
    params = {"since": "2026-09-12T10:00:00.500000Z", "until": "2026-09-12T12:00:00Z"}
    r = client.post("/export", params={"out_dir": str(tmp_path / "exports"), **params})
    assert r.status_code == 200
    summary = r.json()
    assert summary["indices"] == [2, 3]
    assert summary["indices"] == _idx(fixed_store.events(**params))
    bad = client.post("/export", params={"out_dir": str(tmp_path / "bad"), "since": "soon"})
    assert bad.status_code == 422
    assert not (tmp_path / "bad").exists()


def test_cli_export_refuses_garbage_bound_with_exit_2(fixed_store, tmp_path):
    result = CliRunner().invoke(cli_app, [
        "export", "--path", str(fixed_store.path), "--out-dir", str(tmp_path / "x"),
        "--until", "garbage",
    ])
    assert result.exit_code == 2
    assert "until is not an ISO 8601 timestamp" in result.output
    assert not (tmp_path / "x").exists()
    ok = CliRunner().invoke(cli_app, [
        "export", "--path", str(fixed_store.path), "--out-dir", str(tmp_path / "y"),
        "--since", "2026-09-12T11:00:00Z",
    ])
    assert ok.exit_code == 0, ok.output
    assert json.loads(ok.stdout)["indices"] == [2, 3]


def test_stored_ts_that_is_not_iso_fails_a_windowed_read_loudly(tmp_path):
    path = tmp_path / "events.jsonl"
    ev0 = make_event("action", {"i": 0}, prev_hash=GENESIS_HASH, ts=TS[0], event_id="e-0")
    ev1 = make_event("action", {"i": 1}, prev_hash=ev0.hash, ts="yesterday", event_id="e-1")
    path.write_text("".join(e.model_dump_json() + "\n" for e in (ev0, ev1)), encoding="utf-8")
    store = LedgerStore(path)
    assert len(store.events()) == 2  # no window: nothing to parse
    with pytest.raises(ValueError, match="index 1"):
        store.events(since="2026-01-01T00:00:00Z")
    client = TestClient(create_app(store=store), raise_server_exceptions=False)
    assert client.get("/events", params={"since": "2026-01-01T00:00:00Z"}).status_code == 500
