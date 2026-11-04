"""CLAUDE_APPROVER_POLL_SECONDS and _HALT_WAIT_SECONDS must be finite and bounded
(scout proposal S-B3). `float("inf") >= 0` passed `_float_env`; then
`Event.wait(inf)` raises OverflowError and kills the poller thread, and an infinite
halt wait would block /halt."""
from __future__ import annotations

import threading

import pytest

from claude_approver import config


@pytest.mark.parametrize("raw", ["inf", "-inf", "Infinity", "nan", "NaN"])
def test_non_finite_values_give_the_default(monkeypatch, raw):
    monkeypatch.setenv(config.ENV_POLL, raw)
    monkeypatch.setenv(config.ENV_HALT_WAIT, raw)
    assert config.poll_seconds() == config.DEFAULT_POLL_SECONDS
    assert config.halt_wait_seconds() == config.DEFAULT_HALT_WAIT_SECONDS


@pytest.mark.parametrize("raw", ["1e30", "86401", "999999999"])
def test_huge_finite_values_are_clamped_not_passed_through(monkeypatch, raw):
    monkeypatch.setenv(config.ENV_POLL, raw)
    monkeypatch.setenv(config.ENV_HALT_WAIT, raw)
    assert config.poll_seconds() == config.MAX_ENV_SECONDS
    assert config.halt_wait_seconds() == config.MAX_ENV_SECONDS


def test_the_clamped_value_is_waitable(monkeypatch):
    monkeypatch.setenv(config.ENV_POLL, "1e30")
    ev = threading.Event()
    ev.wait(0)                       # sanity: the primitive itself works
    assert config.poll_seconds() <= threading.TIMEOUT_MAX


@pytest.mark.parametrize("raw,want", [("0.75", 0.75), ("30", 30.0), ("86400", 86400.0)])
def test_sane_values_are_unchanged(monkeypatch, raw, want):
    monkeypatch.setenv(config.ENV_POLL, raw)
    monkeypatch.setenv(config.ENV_HALT_WAIT, raw)
    assert config.poll_seconds() == want
    assert config.halt_wait_seconds() == want


def test_the_existing_floor_and_negative_default_still_hold(monkeypatch):
    monkeypatch.setenv(config.ENV_POLL, "0.01")
    assert config.poll_seconds() == config.MIN_POLL_SECONDS
    monkeypatch.setenv(config.ENV_POLL, "-5")
    assert config.poll_seconds() == config.DEFAULT_POLL_SECONDS
