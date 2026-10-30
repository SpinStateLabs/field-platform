"""C-570 (reviewer C-522 F-C522-1/-2): the read cursor is bounded and normalised.

F-C522-1: one event with a far-future ``processed_at`` used to become the cursor and, because nothing is later, stay:
the next read sent ``created_at_gte`` in the far future and the session stopped seeing events without an error. A time
beyond the wall clock plus ``CURSOR_MAX_FUTURE`` (5 minutes) is now counted (``cursor_future_ignored``), logged once
with a fixed text, and not stored.
F-C522-2: the cursor was the raw value, so what was stored was what was sent (a padded string, a date-only value, a
space form, a lower-case ``z``, a naive time). It is now the instant as an aware UTC datetime.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as ns

import pytest

from claude_approver.core import CURSOR_MAX_FUTURE, SessionState

SID = "sesn_c570"
UTC = timezone.utc
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def _client(events, calls=None):
    def _list(**kw):
        if calls is not None:
            calls.append(kw)
        return list(events)
    return ns(beta=ns(sessions=ns(events=ns(list=_list))))


def _ev(n, processed):
    return ns(id=f"e{n}", type="session.status_running", processed_at=processed)


@pytest.fixture
def approver(make_approver):
    return make_approver(wall_clock=lambda: NOW)


@pytest.mark.parametrize("far", ["2999-01-01T00:00:00Z", "9999-12-31T23:59:59+00:00",
                                 datetime(2999, 1, 1, tzinfo=UTC), "2026-11-02T12:00:00Z"])
def test_a_far_future_time_is_not_stored_as_the_cursor(approver, far):
    state = SessionState()
    approver._read_events(_client([_ev(1, "2026-11-01T11:00:00Z"), _ev(2, far)]), SID, state)
    assert state.cursor == datetime(2026, 11, 1, 11, 0, tzinfo=UTC)
    assert approver.counters["cursor_future_ignored"] == 1


def test_a_later_real_time_still_moves_the_cursor_after_a_far_future_one(approver):
    state = SessionState()
    calls: list = []
    approver._read_events(_client([_ev(1, "2999-01-01T00:00:00Z"), _ev(2, "2026-11-01T11:30:00Z")], calls), SID, state)
    approver._read_events(_client([_ev(3, "2026-11-01T11:45:00Z")], calls), SID, state)
    assert state.cursor == datetime(2026, 11, 1, 11, 45, tzinfo=UTC)
    assert calls[-1]["created_at_gte"] == datetime(2026, 11, 1, 11, 30, tzinfo=UTC)     # never the year 2999


def test_with_no_real_time_seen_a_far_future_time_leaves_the_cursor_unset(approver):
    state = SessionState()
    calls: list = []
    approver._read_events(_client([_ev(1, "9999-12-31T23:59:59Z")], calls), SID, state)
    approver._read_events(_client([], calls), SID, state)
    assert state.cursor is None and "created_at_gte" not in calls[-1]


def test_the_skew_bound_is_five_minutes_inclusive(approver):
    assert CURSOR_MAX_FUTURE == timedelta(minutes=5)
    inside, outside = NOW + CURSOR_MAX_FUTURE, NOW + CURSOR_MAX_FUTURE + timedelta(seconds=1)
    state = SessionState()
    approver._read_events(_client([_ev(1, inside)]), SID, state)
    assert state.cursor == inside and "cursor_future_ignored" not in approver.counters
    state = SessionState()
    approver._read_events(_client([_ev(1, outside)]), SID, state)
    assert state.cursor is None and approver.counters["cursor_future_ignored"] == 1


def test_the_future_time_is_logged_once_with_a_fixed_text_and_no_value(approver, caplog):
    state = SessionState()
    with caplog.at_level(logging.WARNING, logger="claude_approver"):
        approver._read_events(_client([_ev(1, "2999-01-01T00:00:00Z"), _ev(2, "2998-01-01T00:00:00Z")]), SID, state)
        approver._read_events(_client([_ev(3, "2997-01-01T00:00:00Z")]), SID, state)
    msgs = [r.getMessage() for r in caplog.records if "cursor" in r.getMessage()]
    assert len(msgs) == 1 and "2999" not in msgs[0] and "2998" not in msgs[0] and "2997" not in msgs[0]
    assert approver.counters["cursor_future_ignored"] == 3


@pytest.mark.parametrize("raw,instant", [
    (" 2026-10-28T13:00:00Z ", datetime(2026, 10, 28, 13, 0, tzinfo=UTC)),
    ("2026-10-28T13:00:00z", datetime(2026, 10, 28, 13, 0, tzinfo=UTC)),
    ("2026-10-28 13:00:00", datetime(2026, 10, 28, 13, 0, tzinfo=UTC)),
    ("2026-10-28T13:00:00", datetime(2026, 10, 28, 13, 0, tzinfo=UTC)),
    ("2026-10-28", datetime(2026, 10, 28, 0, 0, tzinfo=UTC)),
    ("2026-10-28T15:30:00+02:00", datetime(2026, 10, 28, 13, 30, tzinfo=UTC)),
    (datetime(2026, 10, 28, 15, 30, tzinfo=timezone(timedelta(hours=2))), datetime(2026, 10, 28, 13, 30, tzinfo=UTC)),
    (datetime(2026, 10, 28, 13, 0), datetime(2026, 10, 28, 13, 0, tzinfo=UTC)),
])
def test_the_cursor_is_the_instant_as_aware_utc_not_the_raw_spelling(approver, raw, instant):
    state = SessionState()
    calls: list = []
    approver._read_events(_client([_ev(1, raw)], calls), SID, state)
    approver._read_events(_client([], calls), SID, state)
    assert state.cursor == instant and state.cursor.utcoffset() == timedelta(0)
    assert calls[-1]["created_at_gte"] == instant


def test_a_cursor_in_the_past_of_the_clock_is_unaffected(approver):
    state = SessionState()
    approver._read_events(_client([_ev(1, "2000-01-01T00:00:00Z")]), SID, state)
    assert state.cursor == datetime(2000, 1, 1, tzinfo=UTC)
