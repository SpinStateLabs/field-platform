"""The events-read shortcut in ``_approve_session`` and the cursor comparison, one condition at a time (C-412).

The shortcut skips the ``events.list`` read when the session's ``updated_at`` is unchanged, nothing is pending, a read
has happened and the last one is younger than ``EVENTS_REFRESH_SECONDS``. Reviewer C-403 found four of the six
conditions unpinned (F-C403-1) and the ``TypeError`` fallback of ``_later`` never exercised (F-C403-2). Each test
holds every other condition true and the clock inside the interval, so the one condition under test is the only
reason for a second read.
"""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace as ns

from approver_fakes import CONSOLE_AGENT, T0
from claude_approver.core import SessionState, _later

SID = "sesn_guard"


def _reads(console):
    return console.count("events.list")


def test_the_shortcut_is_taken_when_every_condition_holds(console, field, make_approver, mapped):
    """The control: with nothing pending and an unchanged session the second tick does not read again."""
    console.add_session(SID, CONSOLE_AGENT)
    a = make_approver(clock=lambda: 1000.0)
    a.tick()
    a.tick()
    assert _reads(console) == 1


def test_a_pending_ask_forces_a_read_on_every_tick(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    console.idle(SID, event_ids=["evt_other"])               # blocked on something else: nothing is answered, so
    console.ask(SID, "bash")                                 # the session's updated_at stays put and the ask stays open
    a = make_approver(clock=lambda: 1000.0)
    a.tick()
    assert len(a.sessions[SID].asks) == 1 and console.sends() == [] and _reads(console) == 1
    a.tick()
    assert _reads(console) == 2


def test_a_pending_custom_tool_use_forces_a_read_on_every_tick(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    custom = console.add_event(SID, "agent.custom_tool_use", name="mine", input={})
    console.idle(SID, event_ids=[custom.id])
    a = make_approver(clock=lambda: 1000.0)
    a.tick()
    assert a.sessions[SID].customs and not a.sessions[SID].asks and _reads(console) == 1
    a.tick()
    assert _reads(console) == 2


def test_a_session_without_an_updated_time_is_read_on_every_tick(console, field, make_approver, mapped):
    """None == None must not read as "unchanged"."""
    console.add_session(SID, CONSOLE_AGENT)
    console.sessions[SID].updated_at = None
    a = make_approver(clock=lambda: 1000.0)
    a.tick()
    a.tick()
    assert _reads(console) == 2


def test_a_session_never_read_before_is_read_even_when_its_updated_time_matches(console, field, make_approver, mapped):
    """State carried over with a matching ``updated_at`` but no read time yet: the first tick still reads."""
    session = console.add_session(SID, CONSOLE_AGENT)
    a = make_approver(clock=lambda: 1000.0)
    a.sessions[SID] = SessionState(console_id=CONSOLE_AGENT)
    a.sessions[SID].updated_at = session.updated_at
    assert a.sessions[SID].last_read is None
    a.tick()
    assert _reads(console) == 1 and a.sessions[SID].last_read == 1000.0


def test_a_changed_updated_time_forces_a_read(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    a = make_approver(clock=lambda: 1000.0)
    a.tick()
    console.touch(SID)
    a.tick()
    assert _reads(console) == 2


# --- the cursor comparison across types ---------------------------------------------------------------------------

def _events_client(events):
    return ns(beta=ns(sessions=ns(events=ns(list=lambda **kw: list(events)))))


def _ev(n, processed):
    return ns(id=f"e{n}", type="session.status_running", processed_at=processed)


def test_a_datetime_cursor_advances_to_a_later_string_time(make_approver):
    a = make_approver()
    state = SessionState()
    a._read_events(_events_client([_ev(1, T0)]), SID, state)
    later = (T0 + timedelta(days=1)).isoformat()
    a._read_events(_events_client([_ev(2, later)]), SID, state)
    assert state.cursor == later                              # the comparison fell back to text instead of raising


def test_a_string_cursor_advances_to_a_later_datetime_time(make_approver):
    a = make_approver()
    state = SessionState()
    a._read_events(_events_client([_ev(1, "2000-01-01T00:00:00+00:00")]), SID, state)
    a._read_events(_events_client([_ev(2, T0)]), SID, state)
    assert state.cursor == T0


def test_a_mixed_type_cursor_never_moves_back(make_approver):
    a = make_approver()
    state = SessionState()
    a._read_events(_events_client([_ev(1, T0)]), SID, state)
    a._read_events(_events_client([_ev(2, "2000-01-01T00:00:00+00:00")]), SID, state)
    assert state.cursor == T0


def test_later_compares_like_types_directly_and_mixed_types_as_text():
    assert _later(T0 + timedelta(seconds=1), T0) and not _later(T0, T0 + timedelta(seconds=1))
    assert _later("2026-10-27", T0) and not _later("2000-01-01", T0)
