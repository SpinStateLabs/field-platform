"""Scout S-2-15: `DriftTracker.__init__` stored `window_size`, `band` and `baseline_windows` unvalidated.
`baseline_windows=0` made the first completed window average an empty list (ZeroDivisionError at record time, caught by
the gateway as an instrumentation fault and a bypass on every sampled request); `window_size<1` made every score its own
window; a NaN, infinite or non-positive `band` made every window out of band or none. The constructor now refuses them,
with a ValueError that names the argument and never its value. Tests only exercise the tracker; api.py is not touched."""
from __future__ import annotations

import math

import pytest

from force_gateway.drift import DriftTracker

OK = dict(window_size=5, band=0.15, baseline_windows=2)


def make(**over):
    return DriftTracker(**{**OK, **over})


@pytest.mark.parametrize("bad", [0, -1, -10, True, False, 1.5, float("nan"), float("inf"), "5", None])
def test_a_bad_window_size_is_refused_naming_the_argument(bad):
    with pytest.raises(ValueError, match="window_size"):
        make(window_size=bad)


@pytest.mark.parametrize("bad", [0, -1, -10, True, False, 2.5, float("nan"), float("inf"), "2", None])
def test_a_bad_baseline_windows_is_refused_naming_the_argument(bad):
    with pytest.raises(ValueError, match="baseline_windows"):
        make(baseline_windows=bad)


@pytest.mark.parametrize("bad", [0, 0.0, -0.0, -0.1, -1, float("nan"), float("inf"), float("-inf"), True, False, "0.1",
                                 None])
def test_a_bad_band_is_refused_naming_the_argument(bad):
    with pytest.raises(ValueError, match="band"):
        make(band=bad)


@pytest.mark.parametrize("name,bad", [("window_size", -777), ("baseline_windows", -888), ("band", -0.4321)])
def test_the_message_names_the_argument_and_never_the_value(name, bad):
    with pytest.raises(ValueError) as e:
        make(**{name: bad})
    assert name in str(e.value) and str(bad) not in str(e.value)


@pytest.mark.parametrize("kw", [
    dict(window_size=1, baseline_windows=1, band=0.1),
    dict(window_size=1, baseline_windows=1, band=1e-9),
    dict(window_size=100, baseline_windows=50, band=5),
    dict(window_size=2, baseline_windows=2, band=0.15),
    {},
])
def test_good_settings_construct(kw):
    t = DriftTracker(**kw)
    assert t.window_size >= 1 and t.baseline_windows >= 1 and t.band > 0 and math.isfinite(t.band)


def test_the_defaults_are_unchanged():
    t = DriftTracker()
    assert (t.window_size, t.band, t.baseline_windows) == (5, 0.15, 2)


def test_a_one_window_baseline_records_without_dividing_by_zero():
    """The smallest legal baseline works end to end: window 1, baseline 1, then a score outside the band twice alerts."""
    t = DriftTracker(window_size=1, band=0.1, baseline_windows=1)
    assert t.record("r", "d", 0.5, "m", "v1") is None          # the baseline window
    assert t.record("r", "d", 0.9, "m", "v1") is None          # out of band once
    alert = t.record("r", "d", 0.95, "m", "v1")                # out of band twice: the alert
    assert alert is not None and alert.baseline_mean == 0.5
