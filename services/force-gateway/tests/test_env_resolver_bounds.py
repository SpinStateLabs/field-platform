"""S6-20: the two env resolvers cannot be set to a value that breaks serving. ``FORCE_GATEWAY_SENTINEL_TIMEOUT=inf`` put
infinity in ``/health`` (JSON cannot encode it: a 500) and a huge ``FORCE_TELEMETRY_WINDOW`` made ``/telemetry`` an
OverflowError at SQLite's ``LIMIT`` bind. Non-finite or non-positive timeouts are the default and the rest are capped; the
window is 1..MAX; ``create_app``'s explicit arguments get the same check."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from force_gateway.api import (
    DEFAULT_SENTINEL_TIMEOUT, DEFAULT_TELEMETRY_WINDOW, MAX_SENTINEL_TIMEOUT, MAX_TELEMETRY_WINDOW, SentinelClient,
    create_app, mock_upstream, resolve_sentinel_timeout, resolve_telemetry_window,
)

TIMEOUT_ENV, WINDOW_ENV = "FORCE_GATEWAY_SENTINEL_TIMEOUT", "FORCE_TELEMETRY_WINDOW"


def test_the_limits_are_stated():
    assert (MAX_SENTINEL_TIMEOUT, MAX_TELEMETRY_WINDOW) == (600.0, 10_000)


# ---- sentinel timeout --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw", ["inf", "-inf", "Infinity", "1e999", "-1e999", "nan", "NaN", "-1", "0", "-0.0", "", "abc",
                                 "1e-999"], ids=repr)
def test_a_non_finite_non_positive_or_junk_timeout_is_the_default(monkeypatch, raw):
    monkeypatch.setenv(TIMEOUT_ENV, raw)
    assert resolve_sentinel_timeout() == DEFAULT_SENTINEL_TIMEOUT


@pytest.mark.parametrize("raw,expect", [("45", 45.0), ("0.5", 0.5), ("600", 600.0), ("601", 600.0), ("1e6", 600.0),
                                        ("1e300", 600.0), ("5.5", 5.5)])
def test_a_good_timeout_stays_and_a_huge_one_is_capped(monkeypatch, raw, expect):
    monkeypatch.setenv(TIMEOUT_ENV, raw)
    assert resolve_sentinel_timeout() == expect


@pytest.mark.parametrize("value,expect", [(float("inf"), 30.0), (float("nan"), 30.0), (0, 30.0), (-1, 30.0),
                                          (True, 30.0), ("5", 30.0), (45, 45.0), (45.5, 45.5), (10**9, 600.0)],
                         ids=repr)
def test_the_explicit_timeout_gets_the_same_check(value, expect):
    assert create_app(upstream=mock_upstream, sentinel_timeout=value).state.sentinel_timeout == expect
    assert SentinelClient(client=object(), timeout=value).timeout == expect


def test_health_is_200_with_a_finite_timeout_under_every_bad_env(monkeypatch):
    for raw in ("inf", "1e999", "nan", "-1", "0", "1e300"):
        monkeypatch.setenv(TIMEOUT_ENV, raw)
        r = TestClient(create_app(upstream=mock_upstream), raise_server_exceptions=False).get("/health")
        assert r.status_code == 200, (raw, r.status_code)
        t = r.json()["sentinel_timeout_seconds"]
        assert 0 < t <= MAX_SENTINEL_TIMEOUT, (raw, t)


def test_health_with_an_explicit_infinite_timeout_is_200_too():
    c = TestClient(create_app(upstream=mock_upstream, sentinel_timeout=float("inf")), raise_server_exceptions=False)
    assert c.get("/health").status_code == 200


# ---- telemetry window --------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expect", [("99999999999999999999", MAX_TELEMETRY_WINDOW), ("10001", MAX_TELEMETRY_WINDOW),
                                        ("10000", 10_000), ("9999", 9999), ("50", 50), ("1", 1), ("0", 1), ("-5", 1),
                                        ("-99999999999999999999", 1), (" 7 ", 7)])
def test_the_window_is_one_to_the_cap(monkeypatch, raw, expect):
    monkeypatch.setenv(WINDOW_ENV, raw)
    assert resolve_telemetry_window() == expect


@pytest.mark.parametrize("raw", ["", "abc", "1.5", "1e3", "inf", "nan", "0x10"])
def test_a_junk_window_is_the_default(monkeypatch, raw):
    monkeypatch.setenv(WINDOW_ENV, raw)
    assert resolve_telemetry_window() == DEFAULT_TELEMETRY_WINDOW


@pytest.mark.parametrize("value,expect", [(10**30, MAX_TELEMETRY_WINDOW), (0, 1), (-3, 1), (25, 25),
                                          (MAX_TELEMETRY_WINDOW + 1, MAX_TELEMETRY_WINDOW)])
def test_the_explicit_window_gets_the_same_check(value, expect):
    assert create_app(upstream=mock_upstream, telemetry_window=value).state.telemetry_window == expect


@pytest.mark.parametrize("raw", ["99999999999999999999", "10000000000000000000000000", "9223372036854775808"])
def test_telemetry_is_200_under_a_huge_window(monkeypatch, raw):
    monkeypatch.setenv(WINDOW_ENV, raw)
    r = TestClient(create_app(upstream=mock_upstream), raise_server_exceptions=False).get("/telemetry")
    assert r.status_code == 200, r.text[:100]


def test_telemetry_is_200_with_an_explicit_huge_window():
    c = TestClient(create_app(upstream=mock_upstream, telemetry_window=10**30), raise_server_exceptions=False)
    assert c.get("/telemetry").status_code == 200
