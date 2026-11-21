"""tools/fly_snapshot.py: only a COMPLETED snapshot with a real created_at is accepted (B-GL-snapshot-status-values).

Offline, no fly, no network. The inputs are the values the Fly docs show (docs.fly.io/volumes/snapshots and
docs.fly.io/machines/api/volumes-resource, read 2026-11-21) plus the one observed bad snapshot from the estate audit.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import io
import json
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location("fly_snapshot", Path(__file__).resolve().parents[1] / "fly_snapshot.py")
fs = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(fs)

NOW = dt.datetime(2026, 11, 21, 12, 0, 0, tzinfo=dt.timezone.utc)
GOOD = {"id": "vs_a", "status": "created", "created_at": "2026-11-21T11:30:00Z", "size": 123456, "retention_days": 5}


def v(**over):
    return fs.snapshot_complete({**GOOD, **over}, now=NOW)


def test_a_created_snapshot_with_a_real_time_is_accepted():
    r = v()
    assert r.ok and r.code == "ok"


@pytest.mark.parametrize("created_at", [
    "2023-12-02T20:59:35+00:00",                  # the Machines API list example
    "2024-02-16T19:30:43.914350121Z",             # the on-demand backup example (nanoseconds, Z)
    "2026-11-21T06:30:00-05:00",
    "2026-11-21T11:59:59.5Z",
    "2020-01-01T00:00:00Z",                       # the first accepted year
])
def test_the_documented_and_ordinary_time_forms_are_accepted(created_at):
    assert v(created_at=created_at).ok


@pytest.mark.parametrize("status", ["created", " created ", "CREATED", "Created"])
def test_the_completed_status_ignores_case_and_spaces(status):
    assert v(status=status).ok


@pytest.mark.parametrize("status", ["waiting", "running", "WAITING", " Running "])
def test_the_documented_in_progress_states_are_refused_as_in_progress(status):
    r = v(status=status)
    assert not r.ok and r.code == "in-progress"


@pytest.mark.parametrize("status", ["pending", "creating", "complete", "completed", "failed", "error", "deleted",
                                    "prepare", "None", "?", "", "unknown", "created-ish", "not created"])
def test_every_other_status_is_refused_as_not_understood(status):
    r = v(status=status)
    assert not r.ok and r.code == "bad-status"


@pytest.mark.parametrize("status", [None, 1, True, ["created"], {"x": "created"}])
def test_a_status_that_is_not_text_is_refused(status):
    assert v(status=status).code == "bad-status"


def test_a_missing_status_is_refused_and_state_is_read_only_when_status_is_absent():
    snap = {k: val for k, val in GOOD.items() if k != "status"}
    assert fs.snapshot_complete(snap, now=NOW).code == "bad-status"
    assert fs.snapshot_complete({**snap, "state": "created"}, now=NOW).ok            # the backup object's field
    assert fs.snapshot_complete({**snap, "state": "created", "status": "running"}, now=NOW).code == "in-progress"


def test_the_observed_bad_snapshot_is_refused_both_ways():
    r = fs.snapshot_complete({"id": "vs_x", "status": "waiting", "created_at": "0001-01-01T00:00:00Z", "size": 0}, now=NOW)
    assert not r.ok and r.code == "in-progress"
    r = v(created_at="0001-01-01T00:00:00Z")                                             # a completed status cannot rescue it
    assert not r.ok and r.code == "bad-created-at"


@pytest.mark.parametrize("created_at", [
    "0001-01-01T00:00:00Z", "1970-01-01T00:00:00Z", "2019-12-31T23:59:59Z",             # zero, epoch, before 2020
    "2026-11-21T12:06:00Z",                                                            # in the future beyond the skew
    "2026-11-21T11:30:00",                                                             # no offset
    "2026-11-21 11:30:00Z",                                                            # no T
    "2026-13-01T00:00:00Z", "2026-02-30T00:00:00Z", "2026-11-21T25:00:00Z",            # impossible dates
    "5 days ago", "", "null", None, 0, 1763724600, {"a": 1},                            # not a time
])
def test_a_created_at_that_is_not_a_real_recent_time_is_refused(created_at):
    r = v(created_at=created_at)
    assert not r.ok and r.code == "bad-created-at"


def test_a_missing_created_at_is_refused():
    snap = {k: val for k, val in GOOD.items() if k != "created_at"}
    assert fs.snapshot_complete(snap, now=NOW).code == "bad-created-at"


def test_the_future_skew_is_five_minutes_inclusive():
    assert v(created_at="2026-11-21T12:05:00Z").ok
    assert v(created_at="2026-11-21T12:05:01Z").code == "bad-created-at"


def test_max_age():
    old = {**GOOD, "created_at": "2026-11-21T08:00:00Z"}
    assert fs.snapshot_complete(old, now=NOW).ok
    assert fs.snapshot_complete(old, now=NOW, max_age=dt.timedelta(hours=5)).ok
    r = fs.snapshot_complete(old, now=NOW, max_age=dt.timedelta(hours=3))
    assert not r.ok and r.code == "too-old"


@pytest.mark.parametrize("snap", [None, [], "created", 5, [GOOD]])
def test_something_that_is_not_a_snapshot_object_is_refused(snap):
    assert fs.snapshot_complete(snap, now=NOW).code == "not-a-snapshot"


def test_the_size_is_not_part_of_the_rule():
    """Not documented as required, and a snapshot of a volume that holds nothing could be 0: the docs only show 0 B on
    the in-progress row. Status and created_at are what decide."""
    assert v(size=0).ok


@pytest.mark.parametrize("value,expect_none", [
    ("2024-02-16T19:30:43.914350121Z", False), ("2023-12-02T20:59:35+00:00", False), ("2026-11-21T11:30:00", True),
    ("2026-02-30T00:00:00Z", True), (5, True), (None, True)])
def test_parse_created_at(value, expect_none):
    got = fs.parse_created_at(value)
    assert (got is None) == expect_none
    if got is not None:
        assert got.tzinfo is not None


def test_nanoseconds_and_offsets_parse_to_the_right_instant():
    a = fs.parse_created_at("2024-02-16T19:30:43.914350121Z")
    assert a.microsecond == 914350 and a.utcoffset() == dt.timedelta(0)
    b = fs.parse_created_at("2026-11-21T11:30:00-05:00")
    assert b == dt.datetime(2026, 11, 21, 16, 30, tzinfo=dt.timezone.utc)


# ------------------------------------------------------------------------------------------------- the CLI

def run(argv, text):
    out = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(out):
        rc = fs.main(argv, stdin=io.StringIO(text))
    return rc, out.getvalue()


LIST = json.dumps([
    {"id": "vs_old", "status": "created", "created_at": "2026-11-20T10:00:00Z", "size": 5},
    {"id": "vs_new", "status": "waiting", "created_at": "0001-01-01T00:00:00Z", "size": 0},
])


def test_cli_picks_the_id_from_a_list_and_refuses_the_waiting_one():
    rc, out = run(["check", "--id", "vs_new", "--now", "2026-11-21T12:00:00Z"], LIST)
    assert rc == 1 and out.startswith("REFUSED: in-progress")
    rc, out = run(["check", "--id", "vs_old", "--now", "2026-11-21T12:00:00Z"], LIST)
    assert rc == 0 and out.startswith("OK ok")


def test_cli_prefixed_log_lines_before_the_json_are_ignored():
    rc, out = run(["check", "--id", "vs_old", "--now", "2026-11-21T12:00:00Z"], "Updating volume snapshots...\n" + LIST)
    assert rc == 0


def test_cli_max_age():
    rc, out = run(["check", "--id", "vs_old", "--max-age-hours", "1", "--now", "2026-11-21T12:00:00Z"], LIST)
    assert rc == 1 and "too-old" in out


@pytest.mark.parametrize("argv,text,rc", [
    (["check"], LIST, 2),                                       # a list without --id
    (["check", "--id", "vs_none"], LIST, 1),                    # id absent
    (["check", "--id", "vs_old"], json.dumps([json.loads(LIST)[0]] * 2), 1),   # id twice: ambiguous
    (["check"], "no json here", 2),
    (["check"], "", 2),
    (["check", "--now", "garbage"], json.dumps(GOOD), 2),
])
def test_cli_exit_codes_for_the_unusual_inputs(argv, text, rc):
    assert run(argv, text)[0] == rc


def test_cli_a_single_object_needs_no_id_and_a_wrong_id_is_refused():
    assert run(["check", "--now", "2026-11-21T12:00:00Z"], json.dumps(GOOD))[0] == 0
    assert run(["check", "--id", "vs_other", "--now", "2026-11-21T12:00:00Z"], json.dumps(GOOD))[0] == 1


# ------------------------------------------------------------------------- review fixes (PR 1090)

@pytest.mark.parametrize("value", [
    "٢٠٢٦-11-21T11:30:00Z",         # Arabic-Indic digits: not ISO 8601
    "2026-11-21T11:30:00+05:60", "2026-11-21T11:30:00+24:00", "2026-11-21T11:30:00+99:99",
    "2026-11-21T11:30:60Z", "2026-11-21T24:00:00Z", "2026-11-21T11:30:00z", "2026-11-21T11:30:00.Z"])
def test_parse_created_at_refuses_non_iso_forms(value):
    assert fs.parse_created_at(value) is None


def test_max_age_boundary_is_inclusive():
    snap = {**GOOD, "created_at": "2026-11-21T10:00:00Z"}                         # exactly 2 h before NOW
    assert fs.snapshot_complete(snap, now=NOW, max_age=dt.timedelta(hours=2)).ok
    assert fs.snapshot_complete(snap, now=NOW, max_age=dt.timedelta(hours=2) - dt.timedelta(seconds=1)).code == "too-old"


@pytest.mark.parametrize("hours", ["nan", "inf", "-1", "0", "1e9"])
def test_cli_refuses_a_max_age_that_is_not_a_sane_number(hours):
    rc, out = run(["check", "--max-age-hours", hours, "--now", "2026-11-21T12:00:00Z"], json.dumps(GOOD))
    assert rc == 2 and out.startswith("UNREADABLE")


def test_cli_finds_the_json_after_log_lines_that_contain_brackets_and_ignores_what_follows():
    nl = chr(10)
    text = "warn [x] retrying {a}" + nl + "Updating..." + nl + json.dumps(GOOD) + nl + "trailing log line [done]" + nl
    assert run(["check", "--now", "2026-11-21T12:00:00Z"], text)[0] == 0
    assert fs.load_json("x [1, 2] y")[0] == 1                                       # the first value that parses
