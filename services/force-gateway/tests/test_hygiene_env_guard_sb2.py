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
