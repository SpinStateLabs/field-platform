"""C-570 (reviewer C-522 F-C522-1/-2): the events cursor is bounded above and stored normalised.

The cursor goes back to the API as `created_at_gte`. F-C522-1: one event with a far-future `processed_at` became the
cursor and stayed (nothing is later), so the next read asked for events after the year 2999 and the session went
quiet. F-C522-2: the cursor was the raw value, so a padded, date-only, space-separated or basic-format spelling that
Python parses was sent to the API as written."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as ns

import pytest

from claude_approver.core import CURSOR_FUTURE_SLACK, CURSOR_FUTURE_WARN_AFTER, SessionState, _time_or_none

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


def test_the_slack_is_one_minute():
    assert CURSOR_FUTURE_SLACK == timedelta(minutes=1)


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


# --- C-720 (cloud/reviewer C-687 on PR 333) ----------------------------------------------------------------------------


@pytest.mark.parametrize("unusable", ["0001-01-01T00:00:00+05:00", "0001-01-01T00:00:00+14:00",
                                      datetime(1, 1, 1, 0, 0, tzinfo=timezone(timedelta(hours=5))),
                                      datetime(1, 1, 1, 0, 0, tzinfo=timezone(timedelta(hours=1)))])
def test_a_time_with_no_utc_form_is_counted_and_never_escapes_the_read(approver, unusable):
    """F-C687-1: the conversion used to raise OverflowError out of `_read_events`, so the same event was re-read forever."""
    state, client = SessionState(), Recorder()
    read(approver, state, client, _ev(1, unusable))                      # must not raise
    assert state.cursor is None
    assert approver.stats()["cursor_time_unusable"] == 1
    read(approver, state, client, _ev(2, "2026-10-28T12:00:00Z"))        # the next real time still becomes the cursor
    assert state.cursor == "2026-10-28T12:00:00+00:00"


def test_an_unusable_time_after_a_real_cursor_leaves_the_real_one(approver):
    state, client = SessionState(), Recorder()
    read(approver, state, client, _ev(1, "2026-10-28T12:00:00Z"))
    read(approver, state, client, _ev(2, "0001-01-01T00:00:00+05:00"))
    # not later than the cursor, so it is never converted: nothing to count, the real cursor stays
    assert state.cursor == "2026-10-28T12:00:00+00:00" and approver.stats()["cursor_time_unusable"] == 0


def test_a_later_event_in_the_same_batch_is_still_read_after_an_unusable_one(approver):
    state, client = SessionState(), Recorder()
    read(approver, state, client, _ev(1, "0001-01-01T00:00:00+05:00"), _ev(2, "2026-10-28T12:30:00Z"))
    assert state.cursor == "2026-10-28T12:30:00+00:00" and approver.stats()["cursor_time_unusable"] == 1


def test_the_slack_is_one_minute_and_the_window_a_value_inside_it_could_hide_is_one_minute():
    assert CURSOR_FUTURE_SLACK == timedelta(minutes=1)


def test_a_value_just_inside_the_slack_hides_at_most_the_slack(approver):
    state, client = SessionState(), Recorder()
    inside = NOW + CURSOR_FUTURE_SLACK
    read(approver, state, client, _ev(1, inside))
    assert state.cursor == inside                                         # accepted: the hidden window is the slack, 60 s
    assert (inside - NOW) == timedelta(seconds=60)


def test_a_streak_of_values_ahead_of_the_clock_logs_once_per_streak(approver, caplog):
    state, client = SessionState(), Recorder()
    ahead = [_ev(n, NOW + timedelta(minutes=10, seconds=n)) for n in range(CURSOR_FUTURE_WARN_AFTER + 5)]
    with caplog.at_level("WARNING", logger="claude_approver"):
        read(approver, state, client, *ahead)
    warned = [r for r in caplog.records if "check the host clock" in r.getMessage()]
    assert len(warned) == 1 and approver.stats()["cursor_future_ignored"] == CURSOR_FUTURE_WARN_AFTER + 5
    assert "2026" not in warned[0].getMessage()                           # no time value in the line


def test_a_real_time_resets_the_streak_so_a_later_streak_warns_again(approver, caplog):
    state, client = SessionState(), Recorder()
    ahead = lambda base: [_ev(base + n, NOW + timedelta(minutes=10, seconds=n)) for n in range(CURSOR_FUTURE_WARN_AFTER)]
    with caplog.at_level("WARNING", logger="claude_approver"):
        read(approver, state, client, *ahead(0))
        read(approver, state, client, _ev(100, "2026-10-28T12:00:00Z"))
        read(approver, state, client, *ahead(200))
    assert len([r for r in caplog.records if "check the host clock" in r.getMessage()]) == 2


def test_fewer_than_the_warn_threshold_ahead_in_a_row_logs_nothing(approver, caplog):
    state, client = SessionState(), Recorder()
    with caplog.at_level("WARNING", logger="claude_approver"):
        read(approver, state, client, *[_ev(n, NOW + timedelta(minutes=10, seconds=n)) for n in range(CURSOR_FUTURE_WARN_AFTER - 1)])
    assert not [r for r in caplog.records if "check the host clock" in r.getMessage()]


def test_the_readme_says_what_the_counters_mean():
    import pathlib

    readme = (pathlib.Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    assert "one minute ahead" in readme and "THIS HOST'S CLOCK" in readme and "cursor_time_unusable" in readme


def test_the_warning_threshold_is_ten_in_literal_counts(approver, caplog):
    assert CURSOR_FUTURE_WARN_AFTER == 10
    for count, expected in ((9, 0), (10, 1)):
        caplog.clear()
        state, client = SessionState(), Recorder()
        approver._future_streak = 0
        with caplog.at_level("WARNING", logger="claude_approver"):
            read(approver, state, client, *[_ev(n, NOW + timedelta(minutes=10, seconds=n)) for n in range(count)])
        assert len([r for r in caplog.records if "check the host clock" in r.getMessage()]) == expected, count
