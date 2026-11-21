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
import urllib.request
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


class _PlainEstate(ep.Estate):
    """Estate whose `call` is ONE request through ep._OPENER and carries no `_retries_503` marker.

    These tests exercise THIS module's retry wrapper, so they must not depend on whether the real
    ep.Estate.call retries 503 itself (the probe-retry-after change sets the marker on it, which makes
    this module wrap nothing by design). The marker rule is tested separately on fakes."""

    def call(self, method, path, body=None, **kw):
        req = urllib.request.Request(f"{self.base}{path}", method=method)
        try:
            with ep._OPENER.open(req, timeout=self.timeout) as resp:
                raw, status = resp.read(), resp.status
        except urllib.error.HTTPError as exc:
            raw, status = b"", exc.code
        except Exception as exc:
            return 0, {"transport_error": type(exc).__name__}
        return status, json.loads(raw) if raw else None


def test_the_stub_estate_never_carries_the_marker():
    assert not getattr(_PlainEstate("http://127.0.0.1:1", None).call, pgc.RETRY_MARK, False)


@pytest.fixture
def env(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(pgc, "_sleep", clock.sleep)
    monkeypatch.setattr(pgc, "_clock", clock.now)
    monkeypatch.setattr(ep, "RESULTS", [])

    def make(script):
        op = _Opener(script)
        monkeypatch.setattr(ep, "_OPENER", op)
        return pgc._with_503_retry(_PlainEstate("http://127.0.0.1:1", None)), op

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
    estate = pgc._with_503_retry(_PlainEstate("http://127.0.0.1:1", None))
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


# -- changed in response to the review (R-PR1098-2c7d2d6) ---------------------------------


def test_default_backoff_is_exactly_1_2_4_seconds(env):
    make, clock = env
    estate, op = make([503])                           # no Retry-After header, 503 forever
    assert estate.call("GET", "/ledger/events")[0] == 503
    assert clock.sleeps == [1.0, 2.0, 4.0] and len(op.calls) == 4


def test_each_unusable_retry_after_starts_the_default_ladder_at_one_second(env):
    make, clock = env
    estate, op = make([(503, "soon"), (503, "-5"), (503, ""), [{"a": 1}]])
    assert ep._events(estate) == [{"a": 1}]
    assert clock.sleeps == [1.0, 2.0, 4.0]


def test_retry_after_zero_is_floored_so_it_is_not_a_burst(env):
    make, clock = env
    estate, op = make([(503, 0)])
    assert estate.call("GET", "/ledger/events")[0] == 503
    assert clock.sleeps == [pgc.MIN_WAIT_S] * 3 and pgc.MIN_WAIT_S == 0.05
    assert len(op.calls) == 4


def test_the_opener_is_restored_after_every_call_including_an_exception(env, monkeypatch):
    make, clock = env
    estate, op = make([[{"a": 1}]])
    assert ep._OPENER is op
    estate.call("GET", "/ledger/events")
    assert ep._OPENER is op                            # restored after a normal call

    class Boom:
        def open(self, req, timeout=None):
            raise RuntimeError("boom")

    boom = Boom()
    monkeypatch.setattr(ep, "_OPENER", boom)
    assert estate.call("GET", "/ledger/events")[0] == 0   # transport error is returned, not raised
    assert ep._OPENER is boom

    def raising(*a, **kw):
        raise KeyboardInterrupt

    inner = pgc._with_503_retry(type("E", (), {"call": staticmethod(raising)})())
    monkeypatch.setattr(ep, "_OPENER", op)
    with pytest.raises(KeyboardInterrupt):
        inner.call("GET", "/x")
    assert ep._OPENER is op                            # restored after an exception


def test_a_second_call_does_not_double_wrap_so_retries_do_not_nest(env):
    make, clock = env
    estate, op = make([(503, 0)])
    for _ in range(2):
        del op.calls[:]
        assert estate.call("GET", "/ledger/events")[0] == 503
        assert len(op.calls) == 4                      # never 16


def test_wrapping_an_estate_twice_is_one_layer(env):
    make, clock = env
    estate, op = make([(503, 0)])
    first = estate.call
    assert pgc._with_503_retry(estate) is estate and estate.call is first   # not re-wrapped
    estate.call("GET", "/ledger/events")
    assert len(op.calls) == 4


def test_the_opener_wrapper_does_not_wrap_an_already_wrapped_opener():
    base = object()
    once = pgc._Retry503Opener(base)
    assert pgc._Retry503Opener(once).inner is base


def test_an_estate_whose_call_already_retries_is_not_wrapped(env, monkeypatch):
    """The rule: ep.Estate.call carrying `_retries_503` (set by the layer that retries inside
    Estate.call) means this module adds nothing, so the layers can never nest."""
    make, clock = env
    requests = []

    class Inner:
        def open(self, req, timeout=None):
            requests.append(req.get_method())
            raise _http_error(503, 0)

    monkeypatch.setattr(ep, "_OPENER", Inner())

    class RetryingEstate:
        def call(self, method, path, body=None, **kw):     # stands in for Estate.call with its own retry
            for _ in range(4):
                try:
                    ep._OPENER.open(urllib.request.Request("http://127.0.0.1:1" + path, method=method))
                except urllib.error.HTTPError:
                    pass
            return 503, None

        call._retries_503 = True

    est = RetryingEstate()
    assert pgc._with_503_retry(est) is est
    assert "call" not in vars(est)                     # not replaced
    assert est.call("GET", "/ledger/events")[0] == 503
    assert len(requests) <= 4                          # the inner layer's 4, not 4 x 4


def test_a_marked_estate_class_is_detected_through_the_bound_method(env, monkeypatch):
    class Marked:
        def call(self, *a, **kw):
            return 200, None

        call._retries_503 = True

    est = Marked()
    assert pgc._with_503_retry(est) is est and "call" not in vars(est)


def test_make_estate_returns_an_estate_whose_call_is_wrapped_or_already_retries():
    est = pgc._make_estate("http://127.0.0.1:1", None)
    assert getattr(est.call, pgc.RETRY_MARK, False)    # whichever layer retries, exactly one is marked


def test_a_call_with_the_marker_is_not_wrapped_even_on_a_real_estate_subclass(monkeypatch):
    class Marked(ep.Estate):
        def call(self, *a, **kw):
            return 200, None

        call._retries_503 = True

    est = Marked("http://127.0.0.1:1", None)
    assert pgc._with_503_retry(est) is est and "call" not in vars(est)
