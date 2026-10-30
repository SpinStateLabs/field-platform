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


# ------------------------------------------------ C-419 (reviewer C-413 F-C413-1 and the surviving mutants)

from datetime import datetime, timezone  # noqa: E402

from approver_fakes import FakeAPIError  # noqa: E402
from claude_approver.core import EVENTS_REFRESH_SECONDS  # noqa: E402

UTC = timezone.utc


def test_mixed_types_are_ordered_as_times_inside_one_calendar_day():
    """The old text fallback called an EARLIER string later than a datetime of the same day ("T" sorts after " ")."""
    noon = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
    assert not _later("2026-10-28T01:00:00+00:00", noon) and _later(noon, "2026-10-28T01:00:00+00:00")
    assert _later("2026-10-28T23:00:00+00:00", noon) and not _later(noon, "2026-10-28T23:00:00+00:00")
    assert _later("2026-10-28T12:00:00.000001+00:00", noon) and not _later("2026-10-28T11:59:59.999999+00:00", noon)


def test_mixed_types_read_a_z_suffix_and_a_naive_time_as_utc():
    noon = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
    assert _later("2026-10-28T13:00:00Z", noon) and not _later("2026-10-28T11:00:00Z", noon)
    assert _later("2026-10-28T13:00:00", noon) and not _later("2026-10-28T11:00:00", noon)        # naive = UTC
    assert _later(datetime(2026, 10, 28, 13, 0), "2026-10-28T12:00:00+00:00")                       # naive datetime too
    assert not _later(noon, "2026-10-28T12:00:00+00:00")                                            # equal is not later


def test_a_value_that_is_not_a_time_still_falls_back_to_text_and_never_raises():
    noon = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
    assert _later("zzz-not-a-time", noon) is True and _later("0", noon) is False      # text order, as before
    assert _later(7, noon) in (True, False)                                          # an int vs a datetime: no TypeError


def test_a_datetime_cursor_is_not_moved_back_by_an_earlier_string_on_the_same_day(make_approver):
    a = make_approver()
    state = SessionState()
    noon = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
    a._read_events(_events_client([_ev(1, noon)]), SID, state)
    a._read_events(_events_client([_ev(2, "2026-10-28T01:00:00+00:00")]), SID, state)
    assert state.cursor == noon
    a._read_events(_events_client([_ev(3, "2026-10-28T23:00:00+00:00")]), SID, state)
    assert state.cursor == "2026-10-28T23:00:00+00:00"


def test_a_string_cursor_is_not_moved_back_by_an_earlier_datetime_on_the_same_day(make_approver):
    a = make_approver()
    state = SessionState()
    a._read_events(_events_client([_ev(1, "2026-10-28T23:00:00+00:00")]), SID, state)
    a._read_events(_events_client([_ev(2, datetime(2026, 10, 28, 12, 0, tzinfo=UTC))]), SID, state)
    assert state.cursor == "2026-10-28T23:00:00+00:00"


# --- the refresh interval is measured from the LAST read -------------------------------------------------------

def test_the_refresh_interval_runs_from_the_last_read_not_the_first(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    t = [1000.0]
    a = make_approver(clock=lambda: t[0])
    a.tick()                                                         # read 1 at 1000
    assert _reads(console) == 1
    t[0] = 1000.0 + EVENTS_REFRESH_SECONDS - 1
    a.tick()
    assert _reads(console) == 1                                      # still inside the interval
    t[0] = 1000.0 + EVENTS_REFRESH_SECONDS
    a.tick()                                                         # read 2 at 1060: the interval is over
    assert _reads(console) == 2
    t[0] = 1000.0 + EVENTS_REFRESH_SECONDS + EVENTS_REFRESH_SECONDS - 1
    a.tick()                                                         # 59 s after the LAST read: skipped
    assert _reads(console) == 2
    t[0] = 1000.0 + 2 * EVENTS_REFRESH_SECONDS
    a.tick()
    assert _reads(console) == 3


def test_thirty_seconds_after_a_read_still_skips(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    t = [1000.0]
    a = make_approver(clock=lambda: t[0])
    a.tick()
    t[0] += 30.0
    a.tick()
    assert _reads(console) == 1 and EVENTS_REFRESH_SECONDS > 30.0


def test_a_failed_read_returns_zero_and_leaves_the_session_state_alone(console, field, make_approver, mapped):
    console.add_session(SID, CONSOLE_AGENT)
    console.fail["events.list"] = FakeAPIError(529)
    a = make_approver(clock=lambda: 1000.0)
    a.tick()
    state = a.sessions[SID]
    assert state.updated_at is None and state.last_read is None and state.cursor is None
    assert a.stats()["list_failures"] == 1
    del console.fail["events.list"]
    a.tick()
    assert _reads(console) == 2                                       # the failed read never counted as a read
    assert a.sessions[SID].last_read == 1000.0
