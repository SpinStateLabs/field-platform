"""S5-1: FIELD_WITNESS_EVERY is read as ASCII digits only and bounded; a bad value is the 'misconfigured' finding, never an exception.

`str.isdigit()` is True for '²' (superscript two) but `int('²')` raises ValueError, so the old guard crashed the sweep."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from lifecycle_manager.engine import (
    MAX_WITNESS_EVERY_SECONDS,
    LifecycleEngine,
    WitnessWatch,
    witness_watch_from_env,
)

NOW = datetime.now(timezone.utc).replace(microsecond=0)
ROSTER = "owner\nAP Team Lead\n"


def env(raw):
    return {"FIELD_WITNESS_EVERY": raw}


@pytest.mark.parametrize("raw", [
    "²", "³", "¹", "٣", "٣x", "x٣", "０", "１２", "①", "0", "00", "-5", "+5", "1.5", "1e3", "0x10", "1_000", "5 5",
    "9" * 40, str(MAX_WITNESS_EVERY_SECONDS + 1),
])
def test_an_unusable_value_is_a_misconfigured_watch_not_an_exception(raw):
    watch = witness_watch_from_env(env(raw))
    assert watch is not None and watch.every_seconds is None and watch.raw_every == raw.strip()


@pytest.mark.parametrize("raw,expected", [("300", 300), ("  300 ", 300), ("1", 1), ("0003600", 3600),
                                          (str(MAX_WITNESS_EVERY_SECONDS), MAX_WITNESS_EVERY_SECONDS)])
def test_a_usable_value_is_read_as_before(raw, expected):
    assert witness_watch_from_env(env(raw)) == WitnessWatch(every_seconds=expected, estate_watched="fly", raw_every=raw.strip())


@pytest.mark.parametrize("raw", ["", " ", "\t\n"])
def test_blank_is_no_witness(raw):
    assert witness_watch_from_env(env(raw)) is None


def test_the_bound_is_one_billion_seconds_and_three_times_it_still_fits_a_timedelta():
    assert MAX_WITNESS_EVERY_SECONDS == 10**9


class _Registry:
    def list_agents(self, *a, **k):
        return []


class _NoTokens:
    def get(self, *a, **k):
        return []


class _Ledger:
    def append(self, *a, **k):
        pass

    def events(self, event_type=None):
        return []


@pytest.mark.parametrize("raw", ["²", "9" * 40, str(MAX_WITNESS_EVERY_SECONDS + 1)])
def test_the_sweep_reports_misconfigured_and_does_not_crash(raw):
    watch = witness_watch_from_env(env(raw))
    report = LifecycleEngine(registry=_Registry(), delegation=_NoTokens(), ledger=_Ledger(),
                             witness=watch).sweep(ROSTER, now=NOW)
    assert report.witness is not None and report.witness.status == "misconfigured"
    assert report.witness.every_seconds is None


def test_the_largest_allowed_interval_does_not_overflow_the_staleness_math():
    watch = witness_watch_from_env(env(str(MAX_WITNESS_EVERY_SECONDS)))
    report = LifecycleEngine(registry=_Registry(), delegation=_NoTokens(), ledger=_Ledger(),
                             witness=watch).sweep(ROSTER, now=NOW)
    assert report.witness is not None and report.witness.status == "none"   # no anchors: a finding, not an OverflowError
