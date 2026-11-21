"""B-GL-attest-pack-gate: the reporter's own upstream calls honour a 503 + Retry-After within a bounded budget.

A busy ledger (PR 1089: one whole-ledger request at a time) answers a second whole-ledger read 503 with Retry-After.
Inside ``PackEngine.build`` the reporter waits that long and asks again, up to MAX_RETRIES_PER_CALL times per call and
FIELD_ATTEST_RETRY_BUDGET_S seconds in all per build (default 20, 0 = never retry), each wait capped at
RETRY_AFTER_CAP_S. Only a 503 with an integer-seconds Retry-After is retried; every other status, a missing or
unparseable header, and a 503 on a direct ``_fetch`` outside a build behave as before. Applies to every upstream
call. In practice only the ledger's /verify matters: it is the one whole-ledger read a pack sends (every /events query
it sends is filtered, so the ledger's gate never refuses it). A budget of 0 never retries, even for Retry-After: 0.

No real sleeping: ``engine._sleep`` is replaced and records the waits.
"""

from __future__ import annotations

import pytest

from attestation_reporter import engine as eng

ENV = "FIELD_ATTEST_RETRY_BUDGET_S"


class Resp:
    def __init__(self, status, body=None, headers=None):
        self.status_code = status
        self._body = body
        self.headers = headers or {}

    def json(self):
        return self._body


class FakeLedger:
    """Answers per path from a script: path -> list of Resp (the last one repeats)."""

    def __init__(self, script=None, default=None):
        self.script = {k: list(v) for k, v in (script or {}).items()}
        self.default = default if default is not None else Resp(200, [])
        self.calls: list[str] = []

    def get(self, target):
        self.calls.append(target)
        path = target.split("?")[0]
        queue = self.script.get(path)
        if queue:
            return queue.pop(0) if len(queue) > 1 else queue[0]
        return self.default


@pytest.fixture()
def sleeps(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    waited: list[float] = []
    monkeypatch.setattr(eng, "_sleep", lambda s: waited.append(s))
    return waited


def build(ledger):
    return eng.PackEngine(ledger=ledger).build()


def metric(pack, name):
    return next(m for m in pack.all_metrics() if m.name == name)


BUSY2 = Resp(503, None, {"Retry-After": "2"})
VERIFY_OK = Resp(200, {"ok": True, "length": 3, "first_break_index": None, "reason": None, "segments": 1,
                       "archived_segments": 0, "verified_events": 3, "break_segment": None})


def test_a_503_with_retry_after_on_events_is_waited_out_and_retried(sleeps):
    ledger = FakeLedger({"/events": [BUSY2, BUSY2, Resp(200, [])]})
    pack = build(ledger)
    assert sleeps and sleeps[:2] == [2, 2]
    assert metric(pack, "Conformance ALLOW verdicts").status == "ok"


def test_a_503_with_retry_after_on_verify_is_waited_out_and_retried(sleeps):
    ledger = FakeLedger({"/verify": [BUSY2, VERIFY_OK]})
    pack = build(ledger)
    assert sleeps == [2]
    assert [c for c in ledger.calls if c.startswith("/verify")] == ["/verify", "/verify"]
    assert any(m.status == "ok" for m in pack.all_metrics() if "integrity" in m.name.lower() or "chain" in m.name.lower())


def test_a_single_call_is_retried_at_most_max_retries_times(sleeps):
    ledger = FakeLedger({"/verify": [BUSY2]})                       # busy for ever
    build(ledger)
    assert [c for c in ledger.calls if c.startswith("/verify")] == ["/verify"] * (1 + eng.MAX_RETRIES_PER_CALL)


def test_the_build_budget_bounds_the_total_waiting(sleeps, monkeypatch):
    monkeypatch.setenv(ENV, "5")
    ledger = FakeLedger({"/events": [BUSY2], "/verify": [BUSY2]})   # everything busy for ever
    pack = build(ledger)
    assert sum(sleeps) <= 5 and sum(sleeps) >= 4
    assert metric(pack, "Conformance ALLOW verdicts").status == "unavailable"     # gave up: unavailable, never zero


def test_a_budget_of_zero_never_retries(sleeps, monkeypatch):
    monkeypatch.setenv(ENV, "0")
    ledger = FakeLedger({"/verify": [BUSY2, VERIFY_OK]})
    build(ledger)
    assert sleeps == [] and [c for c in ledger.calls if c.startswith("/verify")] == ["/verify"]


@pytest.mark.parametrize("raw", ["abc", "-3", "", "1.5", "9" * 5000])
def test_a_bad_budget_is_the_default_twenty(sleeps, monkeypatch, raw):
    monkeypatch.setenv(ENV, raw)
    assert eng.retry_budget_s() == 20


def test_each_wait_is_capped(sleeps):
    ledger = FakeLedger({"/verify": [Resp(503, None, {"Retry-After": "3600"}), VERIFY_OK]})
    build(ledger)
    assert sleeps == [eng.RETRY_AFTER_CAP_S]


@pytest.mark.parametrize("headers", [{}, {"Retry-After": "soon"}, {"Retry-After": "-5"}, {"Retry-After": "1.5"},
                                     {"Retry-After": "Wed, 21 Nov 2026 12:00:00 GMT"}, {"Retry-After": ""}])
def test_a_503_without_a_usable_retry_after_is_not_retried(sleeps, headers):
    ledger = FakeLedger({"/verify": [Resp(503, None, headers), VERIFY_OK]})
    build(ledger)
    assert sleeps == [] and [c for c in ledger.calls if c.startswith("/verify")] == ["/verify"]


@pytest.mark.parametrize("status", [500, 502, 429, 401, 403, 404])
def test_no_other_status_is_retried_even_with_retry_after(sleeps, status):
    ledger = FakeLedger({"/verify": [Resp(status, None, {"Retry-After": "2"}), VERIFY_OK]})
    build(ledger)
    assert sleeps == [] and [c for c in ledger.calls if c.startswith("/verify")] == ["/verify"]


def test_retry_after_zero_retries_at_once(sleeps):
    ledger = FakeLedger({"/verify": [Resp(503, None, {"Retry-After": "0"}), VERIFY_OK]})
    build(ledger)
    assert sleeps == [0] and len([c for c in ledger.calls if c.startswith("/verify")]) == 2


def test_a_direct_fetch_outside_a_build_is_never_retried(sleeps):
    ledger = FakeLedger({"/verify": [BUSY2, VERIFY_OK]})
    data, query, ok, status = eng._fetch_answer(ledger, "http://x", "/verify")
    assert (ok, status) == (False, 503) and sleeps == [] and len(ledger.calls) == 1


def test_the_budget_is_per_build_not_shared_between_builds(sleeps, monkeypatch):
    monkeypatch.setenv(ENV, "2")
    for _ in range(2):
        ledger = FakeLedger({"/verify": [BUSY2, VERIFY_OK]})
        build(ledger)
    assert sleeps == [2, 2]


def test_a_transport_failure_is_not_retried_and_still_marks_the_upstream_down(sleeps):
    class Down(FakeLedger):
        def get(self, target):
            self.calls.append(target)
            raise ConnectionError("down")

    ledger = Down()
    pack = build(ledger)
    assert sleeps == [] and len(ledger.calls) == 1                  # one attempt, then every other metric fails at once
    assert metric(pack, "Conformance ALLOW verdicts").status == "unavailable"


def test_the_busy_reason_text_is_kept_when_the_budget_runs_out(sleeps, monkeypatch):
    monkeypatch.setenv(ENV, "0")
    pack = build(FakeLedger({"/verify": [BUSY2]}))
    assert any("HTTP 503" in (m.note or "") for m in pack.all_metrics())


def test_a_budget_of_zero_never_retries_even_a_retry_after_of_zero(sleeps, monkeypatch):
    """Review: with the budget at 0 a Retry-After of 0 (cost 0) still re-asked three times."""
    monkeypatch.setenv(ENV, "0")
    zero = Resp(503, None, {"Retry-After": "0"})
    ledger = FakeLedger({"/verify": [zero]})
    build(ledger)
    assert sleeps == [] and len([c for c in ledger.calls if c.startswith("/verify")]) == 1


def test_a_budget_that_is_spent_stops_retries_even_for_retry_after_zero(sleeps, monkeypatch):
    monkeypatch.setenv(ENV, "2")
    ledger = FakeLedger({"/verify": [BUSY2, Resp(503, None, {"Retry-After": "0"})]})   # 2 s spent, then 0-second asks
    build(ledger)
    assert sleeps == [2] and len([c for c in ledger.calls if c.startswith("/verify")]) == 2
