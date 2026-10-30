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

import pytest

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


# --- C-419 (reviewer C-413 F-C413-1 and the surviving mutants) -------------------------------------------------------

def test_a_mixed_type_comparison_orders_by_instant_inside_one_day():
    """str(datetime) has a space, an ISO string a `T`: as text the string always wins inside one date."""
    noon = T0                                                       # 2026-10-26 12:00:00+00:00
    assert _later("2026-10-26T13:00:00+00:00", noon) is True
    assert _later("2026-10-26T01:00:00+00:00", noon) is False       # an earlier string is NOT later
    assert _later(noon, "2026-10-26T23:00:00+00:00") is False       # a later string is NOT earlier
    assert _later(noon, "2026-10-26T01:00:00+00:00") is True
    assert _later("2026-10-26T13:00:00Z", noon) is True             # a trailing Z reads as UTC
    assert _later(noon, "2026-10-26T13:00:00Z") is False


def test_a_datetime_cursor_is_not_moved_back_by_an_earlier_string_time_on_the_same_day(make_approver):
    a = make_approver()
    state = SessionState()
    a._read_events(_events_client([_ev(1, T0)]), SID, state)
    a._read_events(_events_client([_ev(2, "2026-10-26T01:00:00+00:00")]), SID, state)
    assert state.cursor == T0
    later = "2026-10-26T13:00:00+00:00"
    a._read_events(_events_client([_ev(3, later)]), SID, state)
    assert state.cursor == later


@pytest.mark.parametrize("a,b,expected", [
    ("zzz", T0, True),                                    # not an instant: text order, as before
    (T0, "zzz", False),
    ("2026-10-26", T0, False),                            # a naive date against an aware datetime: no instant order, text
    (5, "5", False),
])
def test_values_that_are_not_comparable_instants_fall_back_to_text(a, b, expected):
    assert _later(a, b) is expected


# the interval is measured from the LAST read, and a failed read changes nothing

def test_the_shortcut_measures_the_interval_from_the_last_read_not_the_first(console, field, make_approver, mapped):
    from claude_approver.core import EVENTS_REFRESH_SECONDS

    console.add_session(SID, CONSOLE_AGENT)
    now = [1000.0]
    a = make_approver(clock=lambda: now[0])
    a.tick()                                              # read 1 at 1000
    now[0] = 1000.0 + EVENTS_REFRESH_SECONDS + 1
    a.tick()                                              # read 2: last_read moves to 1061
    assert _reads(console) == 2 and a.sessions[SID].last_read == now[0]
    now[0] += EVENTS_REFRESH_SECONDS - 1
    a.tick()                                              # 59 s after the LAST read: inside the interval
    assert _reads(console) == 2
    now[0] += 2
    a.tick()                                              # 61 s after the last read
    assert _reads(console) == 3


@pytest.mark.parametrize("seconds", [1, 5, 30, 59])
def test_a_tick_inside_the_interval_with_nothing_changed_does_not_read(console, field, make_approver, mapped, seconds):
    console.add_session(SID, CONSOLE_AGENT)
    now = [1000.0]
    a = make_approver(clock=lambda: now[0])
    a.tick()
    now[0] += seconds
    a.tick()
    assert _reads(console) == 1


def test_a_failed_events_read_stops_the_tick_and_leaves_the_cursor_and_the_updated_time_alone(
        console, field, make_approver, mapped):
    from approver_fakes import FakeAPIError

    console.add_session(SID, CONSOLE_AGENT)
    console.add_event(SID, "session.status_running")
    now = [1000.0]
    a = make_approver(clock=lambda: now[0])
    a.tick()
    state = a.sessions[SID]
    cursor, updated, last_read = state.cursor, state.updated_at, state.last_read
    assert cursor is not None and updated is not None
    console.touch(SID)                                    # the session moved on: the next tick must read
    console.fail["events.list"] = FakeAPIError(500)
    now[0] += 5
    a.tick()
    assert a.stats()["list_failures"] == 1
    assert (state.cursor, state.updated_at, state.last_read) == (cursor, updated, last_read)
    del console.fail["events.list"]
    now[0] += 1
    a.tick()                                              # the next tick tries again and succeeds
    assert state.updated_at != updated and state.last_read == now[0]


def test_the_real_refresh_interval_is_sixty_seconds_in_literal_seconds(console, field, make_approver, mapped):
    """Pinned in literal seconds, not through the constant: 59 s skips the read, 61 s makes it."""
    from claude_approver.core import EVENTS_REFRESH_SECONDS

    assert EVENTS_REFRESH_SECONDS == 60.0
    console.add_session(SID, CONSOLE_AGENT)
    now = [1000.0]
    a = make_approver(clock=lambda: now[0])
    a.tick()
    now[0] = 1059.0
    a.tick()
    assert _reads(console) == 1
    now[0] = 1061.0
    a.tick()
    assert _reads(console) == 2
