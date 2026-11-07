"""The gateway's hygiene and budget settings are read once at create_app(); a junk
value must fall back to the default, never crash startup and never silently disable
drift detection (scout proposal S-B2). Window 0 made a window per score; band nan
made `abs(mean - baseline) > band` never true."""
from __future__ import annotations

import pytest

from force_gateway.api import create_app

JUNK = ["abc", "", "  ", "nan", "inf", "-inf", "1e999"]


def _app(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return create_app()


@pytest.mark.parametrize("raw", JUNK + ["0", "-3", "2.5"])
def test_hygiene_window_junk_falls_back_to_five(monkeypatch, raw):
    assert _app(monkeypatch, FORCE_HYGIENE_WINDOW=raw).state.drift.window_size == 5


@pytest.mark.parametrize("raw", JUNK + ["0", "-0.1"])
def test_hygiene_band_junk_falls_back(monkeypatch, raw):
    assert _app(monkeypatch, FORCE_HYGIENE_BAND=raw).state.drift.band == 0.15


@pytest.mark.parametrize("raw", JUNK + ["0", "-1", "1.5"])
def test_hygiene_baseline_windows_junk_falls_back_to_two(monkeypatch, raw):
    assert _app(monkeypatch, FORCE_HYGIENE_BASELINE_WINDOWS=raw).state.drift.baseline_windows == 2


@pytest.mark.parametrize("raw", JUNK + ["0", "-5"])
def test_latency_budget_junk_falls_back(monkeypatch, raw):
    assert _app(monkeypatch, FORCE_GATEWAY_LATENCY_BUDGET_MS=raw).state.latency_budget_ms == 250.0


@pytest.mark.parametrize("raw", JUNK + ["-1", "2.5"])
def test_bypass_cooldown_junk_falls_back(monkeypatch, raw):
    assert _app(monkeypatch, FORCE_GATEWAY_BYPASS_COOLDOWN=raw).state.bypass_cooldown == 10


def test_good_values_are_honoured(monkeypatch):
    app = _app(monkeypatch, FORCE_HYGIENE_WINDOW="8", FORCE_HYGIENE_BAND="0.3",
               FORCE_HYGIENE_BASELINE_WINDOWS="3", FORCE_GATEWAY_LATENCY_BUDGET_MS="100",
               FORCE_GATEWAY_BYPASS_COOLDOWN="0")
    assert (app.state.drift.window_size, app.state.drift.band,
            app.state.drift.baseline_windows) == (8, 0.3, 3)
    assert app.state.latency_budget_ms == 100.0
    assert app.state.bypass_cooldown == 0


def test_explicit_arguments_still_win_over_the_environment(monkeypatch):
    app = _app(monkeypatch, FORCE_GATEWAY_BYPASS_COOLDOWN="abc")
    assert create_app(bypass_cooldown=3, latency_budget_ms=5.0).state.bypass_cooldown == 3
    assert app.state.bypass_cooldown == 10


def test_an_explicit_latency_budget_wins_over_a_junk_environment_value(monkeypatch):
    # reviewer-7 on 466004d (mutant A19): the budget argument was passed but never asserted
    app = _app(monkeypatch, FORCE_GATEWAY_LATENCY_BUDGET_MS="abc")
    assert app.state.latency_budget_ms == 250.0                      # junk env: the default
    assert create_app(latency_budget_ms=5.0).state.latency_budget_ms == 5.0


# ---- review C2 on PR 495: a finite, positive value must not switch the check it tunes off ---------------------------------

from force_gateway import api as _api  # noqa: E402


@pytest.mark.parametrize("raw,expected", [("0.999", 0.999), ("0.0001", 0.0001), ("1", 0.15), ("1.0", 0.15), ("1.5", 0.15),
                                          ("100", 0.15), ("1e300", 0.15)])
def test_band_must_be_below_one_because_a_score_difference_never_exceeds_one(monkeypatch, raw, expected):
    monkeypatch.setenv("FORCE_HYGIENE_BAND", raw)
    assert _api._env_float("FORCE_HYGIENE_BAND", 0.15, below=_api.BAND_BELOW) == expected


@pytest.mark.parametrize("name,limit,default", [
    ("FORCE_HYGIENE_WINDOW", "MAX_HYGIENE_WINDOW", 5),
    ("FORCE_HYGIENE_BASELINE_WINDOWS", "MAX_BASELINE_WINDOWS", 2),
    ("FORCE_GATEWAY_BYPASS_COOLDOWN", "MAX_BYPASS_COOLDOWN", 10),
])
def test_integer_settings_accept_their_ceiling_and_refuse_one_more(monkeypatch, name, limit, default):
    ceiling = getattr(_api, limit)
    monkeypatch.setenv(name, str(ceiling))
    assert _api._env_int(name, default, 0, ceiling) == ceiling
    monkeypatch.setenv(name, str(ceiling + 1))
    assert _api._env_int(name, default, 0, ceiling) == default
    monkeypatch.setenv(name, "999999999999")
    assert _api._env_int(name, default, 0, ceiling) == default


def test_the_latency_budget_accepts_its_ceiling_and_refuses_more(monkeypatch):
    ceiling = _api.MAX_LATENCY_BUDGET_MS
    monkeypatch.setenv("FORCE_GATEWAY_LATENCY_BUDGET_MS", str(ceiling))
    assert _api._env_float("FORCE_GATEWAY_LATENCY_BUDGET_MS", 250.0, maximum=ceiling) == ceiling
    for raw in (str(ceiling + 0.01), "1e300", "999999999"):
        monkeypatch.setenv("FORCE_GATEWAY_LATENCY_BUDGET_MS", raw)
        assert _api._env_float("FORCE_GATEWAY_LATENCY_BUDGET_MS", 250.0, maximum=ceiling) == 250.0


def test_the_documented_ceilings_are_the_ones_the_docs_and_the_call_sites_use():
    assert (_api.MAX_HYGIENE_WINDOW, _api.MAX_BASELINE_WINDOWS, _api.MAX_LATENCY_BUDGET_MS, _api.MAX_BYPASS_COOLDOWN,
            _api.BAND_BELOW) == (1000, 100, 60_000.0, 10_000, 1.0)


@pytest.mark.parametrize("env,attr,default", [
    ({"FORCE_HYGIENE_BAND": "1"}, lambda a: a.state.drift.band, 0.15),
    ({"FORCE_HYGIENE_BAND": "1e300"}, lambda a: a.state.drift.band, 0.15),
    ({"FORCE_HYGIENE_WINDOW": "999999999999"}, lambda a: a.state.drift.window_size, 5),
    ({"FORCE_HYGIENE_BASELINE_WINDOWS": "101"}, lambda a: a.state.drift.baseline_windows, 2),
    ({"FORCE_GATEWAY_LATENCY_BUDGET_MS": "1e300"}, lambda a: a.state.latency_budget_ms, 250.0),
    ({"FORCE_GATEWAY_BYPASS_COOLDOWN": "10001"}, lambda a: a.state.bypass_cooldown, 10),
], ids=["band-1", "band-huge", "window-huge", "baseline-101", "budget-huge", "cooldown-10001"])
def test_create_app_falls_back_for_a_value_that_would_switch_the_check_off(monkeypatch, env, attr, default):
    assert attr(_app(monkeypatch, **env)) == default


def test_create_app_honours_values_at_each_ceiling(monkeypatch):
    app = _app(monkeypatch, FORCE_HYGIENE_WINDOW="1000", FORCE_HYGIENE_BAND="0.999", FORCE_HYGIENE_BASELINE_WINDOWS="100",
               FORCE_GATEWAY_LATENCY_BUDGET_MS="60000", FORCE_GATEWAY_BYPASS_COOLDOWN="10000")
    assert (app.state.drift.window_size, app.state.drift.band, app.state.drift.baseline_windows) == (1000, 0.999, 100)
    assert (app.state.latency_budget_ms, app.state.bypass_cooldown) == (60000.0, 10000)
