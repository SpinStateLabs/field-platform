"""S7-24 — the poll and halt-wait env floats accept only finite values in range.
Event.wait(inf) raises OverflowError (reproduced), which would kill the poller thread."""

from __future__ import annotations

import threading

import pytest

from claude_approver import config

CASES = [
    # raw, expected for POLL (default 2.0), expected for HALT_WAIT (default 20.0)
    ("inf", 2.0, 20.0),
    ("-inf", 2.0, 20.0),
    ("nan", 2.0, 20.0),
    ("1e999", 2.0, 20.0),
    ("1e308", 2.0, 20.0),
    (" 5 ", 5.0, 5.0),
    ("", 2.0, 20.0),
    ("abc", 2.0, 20.0),
    ("-1", 2.0, 20.0),
    ("3601", 2.0, 20.0),
    ("601", 601.0, 20.0),
    ("3600", 3600.0, 20.0),
    ("600", 600.0, 600.0),
    ("0", 0.5, 0.0),
]


@pytest.mark.parametrize("raw, poll, halt", CASES)
def test_poll_seconds(monkeypatch, raw, poll, halt):
    monkeypatch.setenv(config.ENV_POLL, raw)
    got = config.poll_seconds()
    assert got == (max(config.MIN_POLL_SECONDS, poll) if poll == 0.5 else poll)
    assert got >= config.MIN_POLL_SECONDS


@pytest.mark.parametrize("raw, poll, halt", CASES)
def test_halt_wait_seconds(monkeypatch, raw, poll, halt):
    monkeypatch.setenv(config.ENV_HALT_WAIT, raw)
    assert config.halt_wait_seconds() == halt


@pytest.mark.parametrize("raw", ["inf", "1e308", "nan"])
def test_the_poll_value_is_always_waitable(monkeypatch, raw):
    monkeypatch.setenv(config.ENV_POLL, raw)
    threading.Event().wait(min(config.poll_seconds(), 0.01))  # never raises OverflowError
    assert config.poll_seconds() <= config.MAX_POLL_SECONDS


def test_the_overflow_the_guard_exists_for():
    with pytest.raises(OverflowError):
        threading.Event().wait(float("inf"))


@pytest.mark.parametrize("raw", ["inf", "-inf", "nan", "1e999"])
def test_the_helper_alone_refuses_non_finite_even_without_a_ceiling(monkeypatch, raw):
    monkeypatch.setenv("X_S7_24", raw)
    assert config._float_env("X_S7_24", 7.0) == 7.0
