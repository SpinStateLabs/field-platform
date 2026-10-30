"""C-257 / C-259 (reviewer C-233 P1, P3): the selection layers, the event-read rules and the usage guards the
mutation round found unpinned. Each test names the branch it pins.

Which open asks are answered is decided by two independent layers (`_read_events`: only `evaluated_permission ==
"ask"` enters `state.asks`; `_approve_session`: only asks the latest `requires_action` idle lists, or all when it lists
none). Mutating one layer alone used to survive because the other still held, so each layer is driven with the other
neutralised."""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace as ns

import httpx
import pytest

from approver_fakes import CONSOLE_AGENT, FIELD_AGENT, T0, FakeAPIError, usage
from claude_approver.core import SessionState

SID = "sesn_sel"


def decided_asks(console):
    return [e.tool_use_id for e in console.events[SID] if e.type == "user.tool_confirmation"]


# --- layer 1: only an "ask" enters the open set ----------------------------------------------------------------


@pytest.mark.parametrize("permission", ["allow", "deny"])
@pytest.mark.parametrize("form", ["no-ids", "lists-it"])
def test_a_tool_use_the_platform_already_decided_is_never_answered(console, field, make_approver, mapped, permission, form):
    console.add_session(SID, CONSOLE_AGENT)
    ev = console.ask(SID, "bash", permission=permission)
    if form == "no-ids":
        console.idle(SID, omit_ids=True)          # layer 2 would answer every open ask: only layer 1 holds
    else:
        console.idle(SID, event_ids=[ev.id])      # even an idle that lists it: layer 1 never admitted it
    a = make_approver()
    a.tick()
    assert console.sends() == [] and field.checks() == []
    assert a.stats()["allowed"] == 0 and a.stats()["denied_total"] == 0


def test_an_ask_beside_decided_tool_uses_is_the_only_one_answered(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    allowed = console.ask(SID, "read", permission="allow")
    asked = console.ask(SID, "bash")
    denied = console.ask(SID, "rm", permission="deny")
    console.idle(SID, omit_ids=True)
    make_approver().tick()
    assert decided_asks(console) == [asked.id]
    assert allowed.id not in decided_asks(console) and denied.id not in decided_asks(console)


# --- layer 2: only an ask the idle event lists (or all, when it lists none) --------------------------------------


def test_an_ask_that_arrives_after_the_idle_event_and_is_not_listed_is_not_answered(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    first = console.ask(SID, "bash")
    console.idle(SID, event_ids=[first.id])
    second = console.ask(SID, "bash")                 # after the idle: the session is not blocked on it yet
    a = make_approver()
    a.tick()
    assert decided_asks(console) == [first.id]
    assert a.stats().get("asks_superseded", 0) == 0   # it is later than the idle, so it is not "superseded" either
    console.idle(SID)                                  # now the API lists what is pending: just the second ask
    a.tick()
    assert decided_asks(console) == [first.id, second.id]


def test_without_event_ids_on_the_idle_event_every_open_ask_is_answered(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    one, two = console.ask(SID, "bash"), console.ask(SID, "bash")
    console.idle(SID, omit_ids=True)
    make_approver().tick()
    assert sorted(decided_asks(console)) == sorted([one.id, two.id])


def test_an_ask_read_before_the_idle_and_not_listed_is_superseded_and_never_answered(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    stale = console.ask(SID, "bash")
    console.idle(SID, event_ids=[])                    # an idle that names nothing: the earlier turn is over
    a = make_approver()
    a.tick()
    assert decided_asks(console) == [] and a.stats()["asks_superseded"] == 1
    console.idle(SID, event_ids=[stale.id])            # even if a later idle names it, it stays stale
    a.tick()
    assert decided_asks(console) == []


# --- the read rules --------------------------------------------------------------------------------------------


def test_an_event_delivered_on_two_reads_is_processed_once(console, field, make_approver, mapped):
    """The read is inclusive (`created_at_gte`), so the boundary event comes back on the next read; `state.seen`
    must keep `state.seq` equal to the number of distinct events."""
    console.add_session(SID, CONSOLE_AGENT)
    ev = console.ask(SID, "bash")
    console.idle(SID, event_ids=[ev.id])
    a = make_approver()
    a.tick()
    console.touch(SID)                                 # force a second, non-fresh read
    a.tick()
    a.tick()
    state = a.sessions[SID]
    assert state.seq == len(state.seen) and state.seq >= 3
    reads = [kw for name, kw in console.calls if name == "events.list"]
    assert len(reads) >= 2 and reads[1].get("created_at_gte") is not None


def test_a_custom_tool_result_clears_the_pending_custom_use_so_later_asks_are_answered(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    custom = console.add_event(SID, "agent.custom_tool_use", name="mine", input={})
    console.add_event(SID, "user.custom_tool_result", custom_tool_use_id=custom.id)
    ask = console.ask(SID, "bash")
    console.idle(SID, event_ids=[ask.id])
    a = make_approver()
    a.tick()
    assert decided_asks(console) == [ask.id]
    assert a.sessions[SID].customs == {}


def test_a_custom_tool_result_clears_the_custom_use_when_the_idle_event_lists_no_ids(console, field, make_approver, mapped):
    """With no `event_ids` nothing is dropped as superseded, so only the result event can clear the custom use."""
    console.add_session(SID, CONSOLE_AGENT)
    custom = console.add_event(SID, "agent.custom_tool_use", name="mine", input={})
    console.add_event(SID, "user.custom_tool_result", custom_tool_use_id=custom.id)
    ask = console.ask(SID, "bash")
    console.idle(SID, omit_ids=True)
    a = make_approver()
    a.tick()
    assert decided_asks(console) == [ask.id] and a.sessions[SID].customs == {}


def test_a_pending_custom_tool_use_leaves_the_session_untouched(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    custom = console.add_event(SID, "agent.custom_tool_use", name="mine", input={})
    ask = console.ask(SID, "bash")
    console.idle(SID, event_ids=[custom.id, ask.id])      # the session is blocked on both: v0 answers neither
    a = make_approver()
    a.tick()
    assert console.sends() == [] and a.stats()["custom_tool_pending"] == 1


def _events_client(events):
    return ns(beta=ns(sessions=ns(events=ns(list=lambda **kw: list(events)))))


def _ev(n, processed):
    return ns(id=f"e{n}", type="session.status_running", processed_at=processed)


def test_the_cursor_takes_the_first_processed_time_and_only_ever_moves_forward(make_approver):
    a = make_approver()
    state = SessionState()
    t = lambda s: T0 + timedelta(seconds=s)
    a._read_events(_events_client([_ev(1, t(5))]), SID, state)
    assert state.cursor == t(5)
    a._read_events(_events_client([_ev(2, t(2))]), SID, state)          # older: the cursor does not go back
    assert state.cursor == t(5)
    a._read_events(_events_client([_ev(3, t(9))]), SID, state)
    assert state.cursor == t(9)


def test_an_event_with_no_processed_time_never_resets_the_cursor(make_approver):
    a = make_approver()
    state = SessionState()
    a._read_events(_events_client([_ev(1, T0 + timedelta(seconds=5))]), SID, state)
    a._read_events(_events_client([_ev(2, None)]), SID, state)
    assert state.cursor == T0 + timedelta(seconds=5)
    fresh = SessionState()
    a._read_events(_events_client([_ev(3, None)]), SID, fresh)
    assert fresh.cursor is None


def test_the_events_shortcut_reads_again_exactly_at_the_refresh_interval(console, field, make_approver, mapped):
    from claude_approver.core import EVENTS_REFRESH_SECONDS

    console.add_session(SID, CONSOLE_AGENT)
    now = [1000.0]
    a = make_approver(clock=lambda: now[0])
    a.tick()
    assert console.count("events.list") == 1
    now[0] += EVENTS_REFRESH_SECONDS - 0.001
    a.tick()
    assert console.count("events.list") == 1             # inside the interval and unchanged: no read
    now[0] += 0.001
    a.tick()
    assert console.count("events.list") == 2             # exactly at the interval: read again


# --- usage: the counters, the snapshot guard, the model, the heartbeat status ------------------------------------

POST = lambda field: field.usage_posts()


@pytest.mark.parametrize("bad", [-1, -500, None, "5", "x", [1], {"a": 1}, float("nan"), -0.5])
def test_a_negative_or_non_numeric_counter_counts_as_zero(console, field, make_approver, mapped, bad):
    console.add_session(SID, CONSOLE_AGENT, use=ns(input_tokens=bad, output_tokens=40, cache_read_input_tokens=bad,
                                                   cache_creation=None, list_cost=None))
    make_approver().tick()
    (post,) = POST(field)
    assert (post["input_tokens"], post["output_tokens"], post["cache_read_tokens"]) == (0, 40, 0)


@pytest.mark.parametrize("bad", [-1, None, "5", float("nan")])
def test_when_every_counter_is_invalid_nothing_is_posted(console, field, make_approver, mapped, bad):
    console.add_session(SID, CONSOLE_AGENT, use=ns(input_tokens=bad, output_tokens=bad, cache_read_input_tokens=bad,
                                                   cache_creation=None, list_cost=None))
    a = make_approver()
    a.tick()
    assert POST(field) == [] and a.stats()["usage_failures"] == 0


def test_a_float_counter_is_truncated_not_rounded_up(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT, use=ns(input_tokens=12.9, output_tokens=0, cache_read_input_tokens=0,
                                                   cache_creation=None, list_cost=None))
    make_approver().tick()
    assert POST(field)[0]["input_tokens"] == 12


def test_a_session_without_usage_and_without_a_usage_event_posts_nothing_and_fails_nothing(console, field, make_approver, mapped):
    s = console.add_session(SID, CONSOLE_AGENT)
    s.usage = None
    a = make_approver()
    a.tick()
    assert POST(field) == []
    st = a.stats()
    assert st["usage_failures"] == 0 and st["usage_posts"] == 0 and st["last_error"] is None


def test_a_session_without_usage_falls_back_to_the_latest_usage_event(console, field, make_approver, mapped):
    s = console.add_session(SID, CONSOLE_AGENT)
    s.usage = None
    console.add_event(SID, "session.usage", usage=usage(70, 7))
    make_approver().tick()
    (post,) = POST(field)
    assert (post["input_tokens"], post["output_tokens"]) == (70, 7)


def test_the_model_comes_from_the_session_agent_snapshot_first(console, field, make_approver, mapped):
    console.add_agent(CONSOLE_AGENT, model="from-agents-retrieve")
    console.add_session(SID, CONSOLE_AGENT, model="from-the-snapshot", use=usage(5, 1))
    make_approver().tick()
    assert POST(field)[0]["model"] == "from-the-snapshot" and console.count("agents.retrieve") == 0


def test_without_a_snapshot_model_the_agent_is_retrieved_once_per_tick_and_its_model_used(console, field, make_approver, mapped):
    console.add_agent(CONSOLE_AGENT, model="from-agents-retrieve")
    console.add_session("s1", CONSOLE_AGENT, model=None, use=usage(5, 1))
    console.add_session("s2", CONSOLE_AGENT, model=None, use=usage(6, 1))
    make_approver().tick()
    assert [p["model"] for p in POST(field)] == ["from-agents-retrieve", "from-agents-retrieve"]
    assert console.count("agents.retrieve") == 1


def test_an_empty_snapshot_model_falls_back_to_the_agent(console, field, make_approver, mapped):
    console.add_agent(CONSOLE_AGENT, model="from-agents-retrieve")
    console.add_session(SID, CONSOLE_AGENT, model=None, use=usage(5, 1))
    console.sessions[SID].agent = ns(id=CONSOLE_AGENT, model=ns(id=""), version=1)
    make_approver().tick()
    assert POST(field)[0]["model"] == "from-agents-retrieve"


def test_an_agent_whose_model_is_a_plain_string_is_read(console, field, make_approver, mapped):
    console.agents[CONSOLE_AGENT] = ns(id=CONSOLE_AGENT, model="plain-string-model")
    console.add_session(SID, CONSOLE_AGENT, model=None, use=usage(5, 1))
    make_approver().tick()
    assert POST(field)[0]["model"] == "plain-string-model"


@pytest.mark.parametrize("agent", [ns(id=CONSOLE_AGENT, model=None), ns(id=CONSOLE_AGENT, model=ns(id="")),
                                   ns(id=CONSOLE_AGENT, model=ns(id=7)), ns(id=CONSOLE_AGENT, model="")])
def test_an_agent_without_a_usable_model_is_unknown(console, field, make_approver, mapped, agent):
    console.agents[CONSOLE_AGENT] = agent
    console.add_session(SID, CONSOLE_AGENT, model=None, use=usage(5, 1))
    make_approver().tick()
    assert POST(field)[0]["model"] == "unknown"


def test_a_failed_agent_retrieve_is_unknown_and_recorded(console, field, make_approver, mapped):
    console.fail["agents.retrieve"] = FakeAPIError(500)
    console.add_session(SID, CONSOLE_AGENT, model=None, use=usage(5, 1))
    a = make_approver()
    a.tick()
    assert POST(field)[0]["model"] == "unknown" and "agents.retrieve failed" in (a.stats()["last_error"] or "")


@pytest.mark.parametrize("code,ok", [(199, False), (200, True), (201, True), (204, True), (299, True),
                                     (300, False), (301, False), (404, False), (500, False)])
def test_the_heartbeat_counts_only_a_2xx_answer(console, field, make_approver, mapped, code, ok):
    console.add_session(SID, CONSOLE_AGENT)
    ev = console.ask(SID, "bash")
    console.idle(SID, event_ids=[ev.id])
    field.heartbeat = lambda r: httpx.Response(code)
    a = make_approver()
    a.tick()
    st = a.stats()
    assert st["heartbeats"] == (1 if ok else 0) and st["heartbeat_failures"] == (0 if ok else 1)
    assert decided_asks(console) == [ev.id]              # the verdict was sent either way
