"""S8-31 — the drift and bypass tuning env vars are validated at app start: a message naming the variable
(never the value) and a ValueError, never a silent clamp, and never a value that quietly breaks the
gateway (window 0, baseline 0 -> ZeroDivisionError per judged request -> bypass; NaN band -> alerts
silently off; a negative band -> always out of band; NaN/negative latency budget). Explicit constructor
arguments (tests pass a negative budget on purpose to trip bypass) are untouched."""

from __future__ import annotations

import math

import pytest

from force_gateway.api import MAX_BYPASS_COOLDOWN, create_app
from force_gateway.drift import DriftTracker

SECRETISH = "7777777-not-a-number"
CASES = {
    "FORCE_HYGIENE_WINDOW": (["0", "-1", "-5", "1.5", "abc", "", " ", "nan", "inf", SECRETISH], ["1", "5", " 7 ", "100"]),
    "FORCE_HYGIENE_BASELINE_WINDOWS": (["0", "-1", "2.5", "abc", "nan", "inf", SECRETISH], ["1", "2", "10"]),
    "FORCE_HYGIENE_BAND": (["-0.1", "-1", "nan", "NaN", "inf", "-inf", "abc", SECRETISH], ["0", "0.0", "0.15", "1", " 0.5 "]),
    "FORCE_GATEWAY_LATENCY_BUDGET_MS": (["0", "0.0", "-1", "-250", "nan", "inf", "-inf", "abc", SECRETISH], ["0.001", "1", "250", "10000.5"]),
    "FORCE_GATEWAY_BYPASS_COOLDOWN": (["-1", "-10", "1.5", "abc", "nan", "inf", str(MAX_BYPASS_COOLDOWN + 1), SECRETISH],
                                      ["0", "1", "10", str(MAX_BYPASS_COOLDOWN)]),
}
ENDS = [(name, bad) for name, (bads, _) in CASES.items() for bad in bads if bad.strip() != ""]
GOODS = [(name, good) for name, (_, goods) in CASES.items() for good in goods]


@pytest.mark.parametrize("name, bad", ENDS)
def test_a_bad_value_refuses_create_app_naming_the_variable_not_the_value(monkeypatch, name, bad):
    monkeypatch.setenv(name, bad)
    with pytest.raises(ValueError) as info:
        create_app()
    assert name in str(info.value)
    if bad.strip() and bad not in ("0", "-1"):
        assert bad not in str(info.value) or len(bad) <= 3        # never the value (short ones can collide)
    assert SECRETISH not in str(info.value)


@pytest.mark.parametrize("name, good", GOODS)
def test_a_valid_value_starts_and_is_used(monkeypatch, name, good):
    monkeypatch.setenv(name, good)
    app = create_app()
    s = app.state
    if name == "FORCE_HYGIENE_WINDOW":
        assert s.drift.window_size == int(good)
    elif name == "FORCE_HYGIENE_BASELINE_WINDOWS":
        assert s.drift.baseline_windows == int(good)
    elif name == "FORCE_HYGIENE_BAND":
        assert s.drift.band == float(good)
    elif name == "FORCE_GATEWAY_LATENCY_BUDGET_MS":
        assert s.latency_budget_ms == float(good)
    else:
        assert s.bypass_cooldown == int(good)


@pytest.mark.parametrize("name", list(CASES))
@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_means_unset_the_default(monkeypatch, name, blank):
    monkeypatch.setenv(name, blank)
    create_app()


def test_unset_uses_the_documented_defaults():
    s = create_app().state
    assert (s.drift.window_size, s.drift.band, s.drift.baseline_windows) == (5, 0.15, 2)
    assert s.latency_budget_ms == 250.0 and s.bypass_cooldown == 10


# --- DriftTracker constructed directly ---------------------------------------------------------------

@pytest.mark.parametrize("kwargs, name", [
    ({"window_size": 0}, "window_size"), ({"window_size": -1}, "window_size"),
    ({"baseline_windows": 0}, "baseline_windows"), ({"baseline_windows": -3}, "baseline_windows"),
    ({"band": -0.01}, "band"), ({"band": math.nan}, "band"), ({"band": math.inf}, "band"),
])
def test_a_bad_drift_tracker_is_refused_naming_the_parameter(kwargs, name):
    with pytest.raises(ValueError, match=name):
        DriftTracker(**kwargs)


@pytest.mark.parametrize("kwargs", [{}, {"window_size": 1, "baseline_windows": 1, "band": 0.0},
                                    {"window_size": 2, "band": 0.15, "baseline_windows": 2}])
def test_a_valid_drift_tracker_is_unchanged(kwargs):
    DriftTracker(**kwargs)


def test_explicit_create_app_arguments_are_not_validated():
    """Existing tests pass a negative budget and a zero cooldown on purpose."""
    s = create_app(latency_budget_ms=-1.0, bypass_cooldown=0).state
    assert s.latency_budget_ms == -1.0 and s.bypass_cooldown == 0


def test_a_zero_window_no_longer_reaches_the_division(monkeypatch):
    """The failure the card names: baseline_windows=0 divided by len([]) from record()."""
    monkeypatch.setenv("FORCE_HYGIENE_BASELINE_WINDOWS", "0")
    with pytest.raises(ValueError, match="FORCE_HYGIENE_BASELINE_WINDOWS"):
        create_app()
