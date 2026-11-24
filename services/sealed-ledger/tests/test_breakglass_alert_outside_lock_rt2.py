"""RT2 (reviewer-10 F2): the observer's break-glass alert is sent OUTSIDE the observer's lock, repeats are coalesced per
subject, and one tick spends a bounded time on alerts. alerts.send can block up to 18 s per alert (3 x 5 s plus back-off), and it
used to run inline inside observe_once while self._lock was held. A slow fake sender stands in for a slow ntfy."""

from __future__ import annotations

import threading
import time

import pytest

from sealed_ledger import operator_observer as obs


def _health(auth, attempt):
    return {"ok": True, "operator_mode": "log-only", "operator_registry_sha256_prefix": "0123456789abcdef",
            "operator_registry_rows": 4, "operator_registry_generation": 1,
            "breakglass_auth_count": auth, "breakglass_attempt_count": attempt}


class Recorder:
    def __init__(self):
        self.events = []

    def __call__(self, event_type, payload):
        self.events.append((event_type, payload))


def _observer(answers, alert, **kw):
    return obs.OperatorObserver(
        append=Recorder(), self_health=lambda: _health(None, None) | {"breakglass_auth_count": None},
        targets=[(name, f"http://{name}") for name in answers],
        fetch=lambda url: answers.get(url.removesuffix("/health").removeprefix("http://")), alert=alert, **kw)


def test_the_observer_lock_is_not_held_while_an_alert_is_sent():
    answers = {"killswitch": _health(0, 0)}
    seen = []

    def alert(event_type, payload):
        got = o._lock.acquire(blocking=False)
        seen.append(got)
        if got:
            o._lock.release()

    o = _observer(answers, alert)
    o.observe_once()
    answers["killswitch"] = _health(0, 1)
    o.observe_once()
    assert seen == [True]


def test_a_second_tick_is_not_blocked_by_a_slow_alert_in_the_first():
    answers = {"killswitch": _health(0, 0)}
    entered, release = threading.Event(), threading.Event()

    def slow(event_type, payload):
        entered.set()
        release.wait(20)

    o = _observer(answers, slow)
    o.observe_once()
    answers["killswitch"] = _health(0, 1)
    first = threading.Thread(target=o.observe_once, daemon=True)
    first.start()
    assert entered.wait(5), "the alert was never sent"
    done = threading.Event()
    second = threading.Thread(target=lambda: (o.observe_once(), done.set()), daemon=True)
    second.start()
    try:
        assert done.wait(5), "the second tick waited for the slow alert: the lock is held while alerting"
    finally:
        release.set()
        first.join(5)
        second.join(5)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_one_tick_spends_a_bounded_time_on_alerts_and_the_rest_wait_for_the_next_tick():
    answers = {n: _health(0, 0) for n in ("a", "b", "c")}
    clock, sent = FakeClock(), []

    def alert(event_type, payload):
        sent.append(payload["service"])
        clock.now += 10.0                                   # each alert takes 10 s

    o = _observer(answers, alert, clock=clock, alert_budget_seconds=15.0)
    o.observe_once()
    for n in answers:
        answers[n] = _health(0, 1)
    o.observe_once()
    assert sent == ["a", "b"]                               # 10 s used, then 20 s >= 15: the third waits
    o.observe_once()
    assert sent == ["a", "b", "c"]                          # sent once, on the next tick; a and b not repeated
    o.observe_once()
    assert sent == ["a", "b", "c"]


def test_repeats_for_one_subject_are_coalesced_into_the_latest_reading():
    answers = {n: _health(0, 0) for n in ("a", "b")}
    clock, sent = FakeClock(), []

    def alert(event_type, payload):
        sent.append((payload["service"], payload["breakglass_attempt_count"]))
        clock.now += 20.0

    o = _observer(answers, alert, clock=clock, alert_budget_seconds=15.0)
    o.observe_once()
    answers["a"], answers["b"] = _health(0, 1), _health(0, 1)
    o.observe_once()                                        # a is sent (20 s), b is left pending
    answers["b"] = _health(0, 2)                            # b changes again while its alert waits
    o.observe_once()
    answers["b"] = _health(0, 3)
    o.observe_once()
    # b(1) was superseded while it waited: it is never sent; b(2) goes out at the next tick, b(3) at the one after
    assert sent == [("a", 1), ("b", 2), ("b", 3)]


def test_a_raising_alert_does_not_stop_the_other_pending_alerts_or_the_tick():
    answers = {n: _health(0, 0) for n in ("a", "b")}
    sent = []

    def alert(event_type, payload):
        sent.append(payload["service"])
        if payload["service"] == "a":
            raise RuntimeError("sender bug")

    o = _observer(answers, alert)
    o.observe_once()
    answers["a"], answers["b"] = _health(0, 1), _health(0, 1)
    assert o.observe_once() >= 2
    assert sent == ["a", "b"]


def test_an_alert_still_goes_out_in_the_same_tick_that_wrote_the_row():
    """Behaviour kept: for the ordinary case (fast sender) the alert has been sent by the time observe_once returns."""
    answers = {"killswitch": _health(0, 0)}
    sent = []
    o = _observer(answers, lambda e, p: sent.append(p["service"]))
    o.observe_once()
    answers["killswitch"] = _health(1, 0)
    o.observe_once()
    assert sent == ["killswitch"]


def test_default_budget_is_a_few_alerts_worth_not_unbounded():
    assert 0 < obs.ALERT_BUDGET_SECONDS <= 60
