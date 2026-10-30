"""C-570 (reviewer C-522 F-C522-1/-2): the events cursor is bounded above and stored normalised.

The cursor goes back to the API as `created_at_gte`. F-C522-1: one event with a far-future `processed_at` became the
cursor and stayed (nothing is later), so the next read asked for events after the year 2999 and the session went
quiet. F-C522-2: the cursor was the raw value, so a padded, date-only, space-separated or basic-format spelling that
Python parses was sent to the API as written."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as ns

import pytest

from claude_approver.core import CURSOR_FUTURE_SLACK, SessionState, _time_or_none

SID = "sesn_cursor"
NOW = datetime(2026, 10, 28, 13, 0, 0, tzinfo=timezone.utc)


def _ev(n, processed):
    return ns(id=f"e{n}", type="session.status_running", processed_at=processed)


class Recorder:
    """An events client that answers with the given events and records every list call's parameters."""

    def __init__(self):
        self.calls = []
        self.events = []
        self.beta = ns(sessions=ns(events=ns(list=self._list)))

    def _list(self, **kw):
        self.calls.append(kw)
        return list(self.events)


@pytest.fixture
def approver(make_approver):
    return make_approver(wall_clock=lambda: NOW)


def read(approver, state, client, *events):
    client.events = list(events)
    approver._read_events(client, SID, state)


# --- F-C522-1: nothing beyond the clock becomes the cursor -------------------------------------------------------------


@pytest.mark.parametrize("far", ["2999-01-01T00:00:00Z", "9999-12-31T23:59:59Z", datetime(2999, 1, 1, tzinfo=timezone.utc),
                                 "2026-10-28T13:06:00Z", "2026-10-28T15:06:00+02:00"])
def test_a_time_beyond_the_clock_plus_the_slack_is_never_the_cursor_and_is_counted(approver, far):
    state, client = SessionState(), Recorder()
    read(approver, state, client, _ev(1, far))
    assert state.cursor is None
    assert approver.stats()["cursor_future_ignored"] == 1
    read(approver, state, client)
    assert "created_at_gte" not in client.calls[-1]


def test_a_far_future_time_after_a_real_cursor_leaves_the_real_one_and_the_next_read_sends_it(approver):
    state, client = SessionState(), Recorder()
    read(approver, state, client, _ev(1, "2026-10-28T12:00:00Z"))
    read(approver, state, client, _ev(2, "2999-01-01T00:00:00Z"))
    assert state.cursor == "2026-10-28T12:00:00+00:00"
    read(approver, state, client)
    assert client.calls[-1]["created_at_gte"] == "2026-10-28T12:00:00+00:00"       # never the year 2999
    read(approver, state, client, _ev(3, "2026-10-28T12:30:00Z"))
    assert state.cursor == "2026-10-28T12:30:00+00:00"                              # real times still advance it


def test_the_slack_boundary_is_exact(approver):
    state, client = SessionState(), Recorder()
    edge = NOW + CURSOR_FUTURE_SLACK
    read(approver, state, client, _ev(1, edge))                                     # exactly now + slack: accepted
    assert state.cursor == edge and approver.stats()["cursor_future_ignored"] == 0
    state2 = SessionState()
    read(approver, state2, client, _ev(2, edge + timedelta(seconds=1)))             # one second more: ignored
    assert state2.cursor is None and approver.stats()["cursor_future_ignored"] == 1


def test_the_slack_is_five_minutes():
    assert CURSOR_FUTURE_SLACK == timedelta(minutes=5)


def test_the_default_wall_clock_is_the_real_utc_time(make_approver):
    a = make_approver()
    before = datetime.now(timezone.utc)
    moment = a.wall_clock()
    assert before <= moment <= datetime.now(timezone.utc) and moment.tzinfo is not None


# --- F-C522-2: the stored (and sent) value is the normalised instant ---------------------------------------------------


@pytest.mark.parametrize("raw,expected", [
    (" 2026-10-28T12:00:00Z ", "2026-10-28T12:00:00+00:00"),          # padded
    ("2026-10-28", "2026-10-28T00:00:00+00:00"),                      # date only
    ("2026-10-28 12:00:00", "2026-10-28T12:00:00+00:00"),             # space form, naive read as UTC
    ("2026-10-28T12:00:00z", "2026-10-28T12:00:00+00:00"),            # lower-case z
    ("2026-10-28T14:30:00+02:00", "2026-10-28T12:30:00+00:00"),       # another offset, converted
    ("2026-10-28T12:00:00.1234567Z", None),                           # seven fraction digits (Python-version dependent)
    ("20261028T120001Z", None),                                       # basic format (Python 3.11+)
    ("2026-W44-3", None),                                             # week date (Python 3.11+)
])
def test_a_string_cursor_is_stored_and_sent_as_the_normalised_utc_iso_string(approver, raw, expected):
    parsed = _time_or_none(raw)
    if parsed is None:
        pytest.skip("this interpreter does not parse that spelling")
    expected = expected or parsed.astimezone(timezone.utc).isoformat()
    state, client = SessionState(), Recorder()
    read(approver, state, client, _ev(1, raw))
    assert state.cursor == expected
    read(approver, state, client)
    assert client.calls[-1]["created_at_gte"] == expected
    assert state.cursor.endswith("+00:00")


def test_a_datetime_cursor_is_stored_as_an_aware_utc_datetime_of_the_same_instant(approver):
    state, client = SessionState(), Recorder()
    plus_two = datetime(2026, 10, 28, 14, 30, tzinfo=timezone(timedelta(hours=2)))
    read(approver, state, client, _ev(1, plus_two))
    assert state.cursor == plus_two and state.cursor.utcoffset() == timedelta(0)
    naive = datetime(2026, 10, 28, 12, 45)
    read(approver, state, client, _ev(2, naive))
    assert state.cursor == naive.replace(tzinfo=timezone.utc) and state.cursor.tzinfo is not None


def test_a_later_instant_in_another_spelling_replaces_an_earlier_one_and_an_earlier_one_does_not(approver):
    state, client = SessionState(), Recorder()
    read(approver, state, client, _ev(1, "2026-10-28T12:00:00Z"))
    read(approver, state, client, _ev(2, "2026-10-28T13:30:00+02:00"))               # 11:30Z: earlier, ignored
    assert state.cursor == "2026-10-28T12:00:00+00:00"
    read(approver, state, client, _ev(3, " 2026-10-28T12:30:00z "))                  # later, normalised on the way in
    assert state.cursor == "2026-10-28T12:30:00+00:00"


def test_the_stats_report_the_counter_from_the_start(approver):
    assert approver.stats()["cursor_future_ignored"] == 0
