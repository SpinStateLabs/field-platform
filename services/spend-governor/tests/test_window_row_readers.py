"""S10-14: direct tests for the two store readers the rolling throttle depends on, with no HTTP.

`action_rows_after` and `token_rows_after` were reached only through the API in test_throttle.py, which exercises the strict
edge on a frozen clock but not the `actions > 0` filter, the `event_id` tie order or exact-byte action matching at store
level. Each assertion here fails under one of: `>` changed to `>=`, the ORDER BY dropped, the `actions>0` filter dropped,
`cache_read_tokens` added to the sum (hand mutants run when this file was written; see the PR)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from spend_governor.core import GovernorStore
from spend_governor.usage import UsageRecord

T0 = datetime(2026, 11, 7, 12, 0, 0, tzinfo=timezone.utc)
A, B = "agent-a", "agent-b"


def at(seconds):
    return (T0 + timedelta(seconds=seconds)).isoformat()


@pytest.fixture()
def store(tmp_path):
    s = GovernorStore(tmp_path / "spend.sqlite3")
    yield s
    s.close()


def spend(store, agent, seconds, actions, action, source="self", event_id=None):
    """One spend row at T0+seconds. A chosen event_id is inserted directly (record() draws a random uuid)."""
    if event_id is None:
        return store.record(agent, 0, 0, actions, None, T0 + timedelta(seconds=seconds), action=action, source=source)
    with store._lock, store._conn:
        store._conn.execute(
            "INSERT INTO spend (event_id, agent_id, ts, cents, tokens, actions, note, action, source) VALUES (?,?,?,?,?,?,?,?,?)",
            (event_id, agent, at(seconds), 0, 0, actions, None, action, source))


def usage(store, agent, seconds, i, o, cache=0, priced=True, event_id=None):
    store.record_usage(UsageRecord(
        event_id=event_id or f"u-{agent}-{seconds}-{i}-{o}-{cache}", agent_id=agent, ts=at(seconds), model="m",
        input_tokens=i, output_tokens=o, cache_read_tokens=cache,
        cost_units=5 if priced else None, priced=priced))


# -- action_rows_after ---------------------------------------------------------------------------------------------------

def test_the_lower_edge_is_strict_but_the_cap_window_readers_are_inclusive(store):
    spend(store, A, 0, 3, "tool_call")      # exactly on the edge
    spend(store, A, 1, 2, "tool_call")
    assert store.action_rows_after(A, "tool_call", at(0)) == [(at(1), "self", 2)]
    assert store.totals_since(A, at(0))[2] == 5                     # totals_since is ts >= since
    assert dict(((a, s), n) for a, s, n in store.action_counts_since(A, at(0))) == {("tool_call", "self"): 5}


def test_rows_come_back_oldest_first_whatever_the_insert_order(store):
    for sec in (30, 10, 20):
        spend(store, A, sec, sec, "tool_call")
    assert [r[0] for r in store.action_rows_after(A, "tool_call", at(0))] == [at(10), at(20), at(30)]


def test_rows_with_the_same_ts_are_ordered_by_event_id(store):
    spend(store, A, 5, 1, "tool_call", event_id="c")
    spend(store, A, 5, 2, "tool_call", event_id="a")
    spend(store, A, 5, 3, "tool_call", event_id="b")
    assert [r[2] for r in store.action_rows_after(A, "tool_call", at(0))] == [2, 3, 1]


def test_a_row_with_zero_actions_is_omitted(store):
    spend(store, A, 1, 0, "tool_call")
    spend(store, A, 2, 4, "tool_call")
    assert store.action_rows_after(A, "tool_call", at(0)) == [(at(2), "self", 4)]


def test_the_action_compare_is_byte_exact(store):
    for n, name in enumerate(("Tool_Call", "tool_call ", "tool_call", " tool_call", "tool_cal\u0131l"), start=1):
        spend(store, A, n, n, name)
    for n, name in enumerate(("Tool_Call", "tool_call ", "tool_call", " tool_call"), start=1):
        assert store.action_rows_after(A, name, at(0)) == [(at(n), "self", n)], repr(name)
    assert store.action_rows_after(A, "TOOL_CALL", at(0)) == []


def test_another_agents_rows_never_appear_and_a_null_action_is_not_a_match(store):
    spend(store, A, 1, 1, "tool_call")
    spend(store, B, 2, 9, "tool_call")
    spend(store, A, 3, 5, None)
    assert store.action_rows_after(A, "tool_call", at(0)) == [(at(1), "self", 1)]
    assert store.action_rows_after(B, "tool_call", at(0)) == [(at(2), "self", 9)]
    assert store.action_rows_after("nobody", "tool_call", at(0)) == []


def test_the_source_column_round_trips(store):
    spend(store, A, 1, 1, "tool_call", source="self")
    spend(store, A, 2, 1, "tool_call", source="sentinel")
    assert [(r[1]) for r in store.action_rows_after(A, "tool_call", at(0))] == ["self", "sentinel"]


# -- token_rows_after ----------------------------------------------------------------------------------------------------

def test_token_rows_sum_input_and_output_and_exclude_cache_reads(store):
    usage(store, A, 1, 100, 20, cache=5000)
    assert store.token_rows_after(A, at(0)) == [(at(1), 120)]


def test_token_rows_lower_edge_is_strict_but_window_tokens_is_inclusive(store):
    usage(store, A, 0, 10, 1)
    usage(store, A, 1, 20, 2)
    assert store.token_rows_after(A, at(0)) == [(at(1), 22)]
    assert store.window_tokens(A, at(0)) == 33


def test_token_rows_order_and_tie_order_by_event_id(store):
    usage(store, A, 30, 3, 0, event_id="z")
    usage(store, A, 10, 1, 0, event_id="y")
    usage(store, A, 20, 20, 0, event_id="x")
    usage(store, A, 20, 21, 0, event_id="w")
    assert store.token_rows_after(A, at(0)) == [(at(10), 1), (at(20), 21), (at(20), 20), (at(30), 3)]


def test_an_unpriced_row_is_still_counted_and_other_agents_are_not(store):
    usage(store, A, 1, 7, 3, priced=False)
    usage(store, B, 2, 100, 100)
    assert store.token_rows_after(A, at(0)) == [(at(1), 10)]
    assert store.token_rows_after("nobody", at(0)) == []
