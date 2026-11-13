"""PR 495 architect ruling: a hygiene or budget setting whose environment value is unusable falls back to its default
(unchanged) AND says so: one WARNING per process per variable naming the variable and the accepted range, never the
value or any part of it (C-582), and the variable NAMES (sorted, no values) in /health ``env_fallbacks``."""
from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from force_gateway import api as _api
from force_gateway.api import create_app

SENTINEL = "ZQ-SENTINEL-4471"          # junk text that must never be echoed
BIG = "987654321012345"                # an over-the-ceiling number that must never be echoed

SETTINGS = {                           # variable -> (default getter, an over-ceiling value)
    "FORCE_HYGIENE_WINDOW": (lambda a: a.state.drift.window_size, 5, "1001"),
    "FORCE_HYGIENE_BAND": (lambda a: a.state.drift.band, 0.15, "1"),
    "FORCE_HYGIENE_BASELINE_WINDOWS": (lambda a: a.state.drift.baseline_windows, 2, "101"),
    "FORCE_GATEWAY_LATENCY_BUDGET_MS": (lambda a: a.state.latency_budget_ms, 250.0, "60000.5"),
    "FORCE_GATEWAY_BYPASS_COOLDOWN": (lambda a: a.state.bypass_cooldown, 10, "10001"),
}


@pytest.fixture(autouse=True)
def _fresh_process_state():
    _api._WARNED_FALLBACKS.clear()
    yield
    _api._WARNED_FALLBACKS.clear()


def _warnings(caplog):
    return [r for r in caplog.records if r.name == "force_gateway" and r.levelno == logging.WARNING
            and "is not usable" in r.getMessage()]


def _make(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return create_app()


@pytest.mark.parametrize("name", sorted(SETTINGS))
@pytest.mark.parametrize("bad", [SENTINEL, "nan", "inf", "-inf", "0", "-1", BIG, "  "])
def test_a_bad_value_gives_the_default_one_warning_and_an_env_fallbacks_entry(monkeypatch, caplog, name, bad):
    if name == "FORCE_GATEWAY_BYPASS_COOLDOWN" and bad == "0":
        pytest.skip("0 is a valid cooldown")
    getter, default, _ = SETTINGS[name]
    caplog.set_level(logging.WARNING, logger="force_gateway")
    app = _make(monkeypatch, **{name: bad})
    assert getter(app) == default
    w = _warnings(caplog)
    assert len(w) == 1 and name in w[0].getMessage(), [r.getMessage() for r in w]
    assert app.state.env_fallbacks == [name]
    assert TestClient(app).get("/health").json()["env_fallbacks"] == [name]


@pytest.mark.parametrize("name", sorted(SETTINGS))
def test_a_value_over_the_ceiling_gives_the_default_and_one_warning(monkeypatch, caplog, name):
    getter, default, over = SETTINGS[name]
    caplog.set_level(logging.WARNING, logger="force_gateway")
    app = _make(monkeypatch, **{name: over})
    assert getter(app) == default
    assert len(_warnings(caplog)) == 1 and app.state.env_fallbacks == [name]


@pytest.mark.parametrize("name", sorted(SETTINGS))
@pytest.mark.parametrize("bad", [SENTINEL, BIG])
def test_the_value_appears_in_no_log_line_no_health_field_and_no_exception_text(monkeypatch, caplog, name, bad):
    caplog.set_level(logging.DEBUG)
    app = _make(monkeypatch, **{name: bad})
    health = TestClient(app).get("/health")
    assert bad not in health.text
    assert all(bad not in r.getMessage() and bad not in str(r.args) and not r.exc_info for r in caplog.records)
    assert bad not in caplog.text
    assert bad not in repr(app.state.env_fallbacks)


@pytest.mark.parametrize("name", sorted(SETTINGS))
def test_the_warning_names_the_variable_and_the_accepted_range(monkeypatch, caplog, name):
    caplog.set_level(logging.WARNING, logger="force_gateway")
    _make(monkeypatch, **{name: SENTINEL})
    text = _warnings(caplog)[0].getMessage()
    assert name in text and "accepted:" in text
    assert any(ch.isdigit() for ch in text.split("accepted:")[1])      # a range, not a bare name


def test_every_setting_that_fell_back_is_named_sorted(monkeypatch):
    env = {n: SENTINEL for n in SETTINGS}
    app = _make(monkeypatch, **env)
    assert app.state.env_fallbacks == sorted(SETTINGS)
    assert TestClient(app).get("/health").json()["env_fallbacks"] == sorted(SETTINGS)


def test_an_unset_empty_or_valid_value_gives_no_warning_and_an_empty_list(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="force_gateway")
    app = create_app()
    assert _warnings(caplog) == [] and app.state.env_fallbacks == []
    assert TestClient(app).get("/health").json()["env_fallbacks"] == []
    app = _make(monkeypatch, FORCE_HYGIENE_WINDOW="7", FORCE_HYGIENE_BAND="0.5", FORCE_HYGIENE_BASELINE_WINDOWS="3",
                FORCE_GATEWAY_LATENCY_BUDGET_MS="100", FORCE_GATEWAY_BYPASS_COOLDOWN="0")
    assert _warnings(caplog) == [] and app.state.env_fallbacks == []
    app = _make(monkeypatch, FORCE_HYGIENE_WINDOW="")                 # a blank variable is an unset one (compose blanks)
    assert _warnings(caplog) == [] and app.state.env_fallbacks == []


def test_one_warning_per_process_not_one_per_app_or_request(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="force_gateway")
    monkeypatch.setenv("FORCE_HYGIENE_BAND", SENTINEL)
    first = create_app()
    second = create_app()
    client = TestClient(second)
    for _ in range(3):
        client.get("/health")
    assert len(_warnings(caplog)) == 1
    assert first.state.env_fallbacks == second.state.env_fallbacks == ["FORCE_HYGIENE_BAND"]    # /health still lists it


def test_each_variable_warns_once_on_its_own(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="force_gateway")
    monkeypatch.setenv("FORCE_HYGIENE_BAND", SENTINEL)
    create_app()
    monkeypatch.setenv("FORCE_HYGIENE_WINDOW", SENTINEL)
    create_app()
    names = sorted(n for r in _warnings(caplog) for n in SETTINGS if n in r.getMessage())
    assert names == ["FORCE_HYGIENE_BAND", "FORCE_HYGIENE_WINDOW"]


def test_an_explicit_argument_wins_and_does_not_warn(monkeypatch, caplog):
    caplog.set_level(logging.WARNING, logger="force_gateway")
    monkeypatch.setenv("FORCE_GATEWAY_LATENCY_BUDGET_MS", SENTINEL)
    monkeypatch.setenv("FORCE_GATEWAY_BYPASS_COOLDOWN", SENTINEL)
    app = create_app(latency_budget_ms=5.0, bypass_cooldown=3)
    assert app.state.latency_budget_ms == 5.0 and app.state.bypass_cooldown == 3   # reviewer-7 A19, the explicit argument
    assert _warnings(caplog) == [] and app.state.env_fallbacks == []
