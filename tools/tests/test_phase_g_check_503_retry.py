"""B-GL-phase-g-check-503: phase_g_check's reads (the ledger/events and ledger/verify calls of
no_leak, collateral and status_pairing, which go through ep._events / ep._ledger ->
ep.Estate.call) survive a transient HTTP 503 with bounded Retry-After handling: at most 3
retries, at most 30 s in total, fail closed at the budget. Offline: the opener and the sleep
are stubbed, no socket is opened and nothing sleeps."""

from __future__ import annotations

import email.message
import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

import estate_probe as ep  # noqa: E402
import phase_g_check as pgc  # noqa: E402


class _Resp:
    def __init__(self, body, status=200):
        self._raw, self.status = json.dumps(body).encode(), status

    def read(self, n=-1):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _http_error(code, retry_after=None):
    hdrs = email.message.Message()
    if retry_after is not None:
        hdrs["Retry-After"] = str(retry_after)
    return urllib.error.HTTPError("http://127.0.0.1:1/x", code, "x", hdrs, io.BytesIO(b'{"detail":"busy"}'))


class _Opener:
    """Scripted: each item is a response body (200), an int status, or a (status, retry_after) pair."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def open(self, req, timeout=None):
        self.calls.append((req.get_method(), req.full_url.split("1", 1)[-1][1:]))
        item = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(item, tuple):
            raise _http_error(*item)
        if isinstance(item, int):
            raise _http_error(item)
        return _Resp(item)


class _Clock:
    def __init__(self):
        self.t, self.sleeps = 1000.0, []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


@pytest.fixture
def env(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(pgc, "_sleep", clock.sleep)
    monkeypatch.setattr(pgc, "_clock", clock.now)
    monkeypatch.setattr(ep, "RESULTS", [])

    def make(script):
        op = _Opener(script)
        monkeypatch.setattr(ep, "_OPENER", op)
        return pgc._with_503_retry(ep.Estate("http://127.0.0.1:1", None)), op

    return make, clock


def test_events_read_retries_a_503_and_honours_retry_after(env):
    make, clock = env
    estate, op = make([(503, 2), (503, 3), [{"event_type": "x"}]])
    assert ep._events(estate, event_type="x") == [{"event_type": "x"}]
    assert clock.sleeps == [2, 3] and len(op.calls) == 3


def test_at_most_three_retries_then_fail_closed(env):
    make, clock = env
    estate, op = make([(503, 1)])  # 503 forever
    assert ep._events(estate) is None                  # never [] : a red check, not an empty ledger
    assert len(op.calls) == 4 and len(clock.sleeps) == 3
    assert [ok for ok, _ in ep.RESULTS] == [False]


def test_total_wait_never_exceeds_thirty_seconds(env):
    make, clock = env
    estate, op = make([(503, 20)])
    status, _ = estate.call("GET", "/ledger/events")
    assert status == 503                               # fail closed at the budget
    assert sum(clock.sleeps) <= 30 and clock.sleeps == [20, 10]
    assert len(op.calls) == 3


def test_a_huge_retry_after_is_capped_by_the_budget(env):
    make, clock = env
    estate, op = make([(503, 3600), [{"a": 1}]])
    assert ep._events(estate) == [{"a": 1}]
    assert clock.sleeps == [30]


@pytest.mark.parametrize("bad", ["soon", "-5", "Wed, 21 Oct 2026 07:28:00 GMT", ""])
def test_missing_or_unusable_retry_after_uses_bounded_default_backoff(env, bad):
    make, clock = env
    estate, op = make([(503, bad), [{"a": 1}]])
    assert ep._events(estate) == [{"a": 1}]
    assert len(clock.sleeps) == 1 and 0 < clock.sleeps[0] <= 30


def test_ledger_chain_read_survives_a_503_on_each_of_its_three_routes(env, monkeypatch):
    make, clock = env
    head = "ab" * 32
    ev = [{"hash": head}]

    class Routed(_Opener):
        n = {"h": 0, "e": 0, "v": 0}

        def open(self, req, timeout=None):
            for key, frag, body in (("h", "/ledger/health", {"event_count": 1, "head_hash": head}),
                                    ("e", "/ledger/events", ev),
                                    ("v", "/ledger/verify", {"ok": True, "length": 1})):
                if req.full_url.endswith(frag):
                    self.n[key] += 1
                    if self.n[key] == 1:
                        raise _http_error(503, 1)
                    return _Resp(body)
            raise AssertionError(req.full_url)

    monkeypatch.setattr(ep, "_OPENER", Routed([]))
    estate = pgc._with_503_retry(ep.Estate("http://127.0.0.1:1", None))
    assert ep._ledger(estate) == ev
    assert clock.sleeps == [1, 1, 1] and all(ok for ok, _ in ep.RESULTS)


@pytest.mark.parametrize("status", [500, 502, 504, 404, 429])
def test_only_503_is_retried(env, status):
    make, clock = env
    estate, op = make([status])
    assert estate.call("GET", "/ledger/events")[0] == status
    assert len(op.calls) == 1 and clock.sleeps == []


def test_a_write_is_never_retried(env):
    make, clock = env
    estate, op = make([(503, 1)])
    assert estate.call("POST", "/killswitch/kill/x", {})[0] == 503
    assert len(op.calls) == 1 and clock.sleeps == []


def test_success_path_is_untouched(env):
    make, clock = env
    estate, op = make([[{"a": 1}]])
    assert ep._events(estate) == [{"a": 1}] and clock.sleeps == [] and len(op.calls) == 1


def test_run_builds_its_estate_through_the_retry_wrapper(monkeypatch):
    seen = {}

    def fake(base, secret):
        seen["args"] = (base, secret)
        raise SystemExit("stop")

    monkeypatch.setattr(pgc, "_make_estate", fake)
    import argparse
    args = argparse.Namespace(base="http://127.0.0.1:1", agent="a", operator_id=None, allow_plaintext=False,
                              restore=False)
    with pytest.raises(SystemExit):
        pgc._run(args, None, None)
    assert seen["args"] == ("http://127.0.0.1:1", None)
