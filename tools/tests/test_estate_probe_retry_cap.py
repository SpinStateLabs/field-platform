"""Estate.call's busy-retry is capped: at most RETRY_MAX (3) retries per call, a floor of RETRY_MIN_WAIT (0.5 s)
between them, and never past the call's --timeout budget (PR 1099 review: an always-503 + Retry-After: 0 ledger
was hit 892 times in 20 s).

Fully offline and socket-free: the HTTP layer is a stub and the clock and sleep are fake, so the request counts
and the total fake time are exact."""

from __future__ import annotations

import email.message
import io
import sys
import urllib.error
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import estate_probe as ep  # noqa: E402

REQUEST_COST = 0.01   # fake seconds one request takes


class World:
    def __init__(self, monkeypatch, retry_after, status=503, ok_after=None):
        self.now, self.requests, self.sleeps = 1000.0, 0, []
        self.retry_after, self.status, self.ok_after = retry_after, status, ok_after
        self.t0 = self.now
        monkeypatch.setattr(ep.time, "monotonic", lambda: self.now)
        monkeypatch.setattr(ep.time, "sleep", self._sleep)
        monkeypatch.setattr(ep._OPENER, "open", self._open)

    def _sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds

    def _open(self, req, timeout=None):
        self.requests += 1
        self.now += REQUEST_COST
        if self.ok_after is not None and self.requests > self.ok_after:
            return _Ok()
        headers = email.message.Message()
        if self.retry_after is not None:
            headers["Retry-After"] = self.retry_after
        raise urllib.error.HTTPError(req.full_url, self.status, "busy", headers, io.BytesIO(b'{"error":"busy"}'))

    @property
    def elapsed(self):
        return round(self.now - self.t0, 6)


class _Ok:
    status = 200

    def read(self, n=-1):
        return b"{}"

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _call(world, timeout=30.0, method="GET"):
    return ep.Estate("http://127.0.0.1:9", None, timeout).call(method, "/ledger/health", auth=False)[0]


# retry_after, requests, total fake seconds (requests * 0.01 + 3 waits), for an always-busy ledger, 30 s budget
@pytest.mark.parametrize("retry_after,requests,elapsed", [
    ("0", 4, 1.54),     # floor 0.5 s x 3
    ("1", 4, 3.04),
    ("5", 4, 15.04),
    (None, 1, 0.01),    # 503 without Retry-After is not a busy signal: never retried
], ids=["ra0", "ra1", "ra5", "absent"])
def test_request_count_and_total_time(monkeypatch, retry_after, requests, elapsed):
    w = World(monkeypatch, retry_after)
    assert _call(w) == 503
    assert w.requests == requests
    assert w.elapsed == pytest.approx(elapsed)


def test_at_most_three_retries_whatever_the_budget(monkeypatch):
    w = World(monkeypatch, "0")
    assert _call(w, timeout=3600.0) == 503
    assert w.requests == 1 + ep.RETRY_MAX == 4


def test_retry_after_zero_waits_at_least_half_a_second(monkeypatch):
    w = World(monkeypatch, "0")
    _call(w)
    assert w.sleeps == [0.5, 0.5, 0.5]
    assert ep.retry_wait("0") == 0.5 and ep.retry_wait("0.1") == 0.5 and ep.retry_wait("2") == 2.0


def test_the_budget_still_bounds_the_retries(monkeypatch):
    w = World(monkeypatch, "5")
    assert _call(w, timeout=12.0) == 503
    assert w.requests == 3 and w.elapsed == pytest.approx(10.03)   # a 3rd wait would end at 15.03 > 12


def test_a_busy_ledger_that_recovers_inside_the_cap_answers(monkeypatch):
    w = World(monkeypatch, "1", ok_after=2)
    assert _call(w) == 200
    assert w.requests == 3 and w.elapsed == pytest.approx(2.03)


def test_a_write_is_never_resent(monkeypatch):
    w = World(monkeypatch, "0")
    assert _call(w, method="POST") == 503 and w.requests == 1


def test_the_worst_case_nested_in_a_wrapper_is_bounded(monkeypatch):
    """phase_g_check (PR 1098) retries around Estate.call: with its own 3 retries the nested worst case is 4 x 4."""
    w = World(monkeypatch, "0")
    est = ep.Estate("http://127.0.0.1:9", None, 30.0)
    for _ in range(4):
        est.call("GET", "/ledger/health", auth=False)
    assert w.requests == 16


def test_estate_call_carries_the_retries_503_marker():
    """phase_g_check adds no retry layer of its own when it sees this marker on estate.call (no nested storm)."""
    est = ep.Estate("http://127.0.0.1:9", None, 1.0)
    assert getattr(est.call, "_retries_503", False) is True
    assert getattr(ep.Estate.call, "_retries_503", False) is True
