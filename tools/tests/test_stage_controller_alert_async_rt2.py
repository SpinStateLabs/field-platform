"""B-RT2 F4 (reviewer-10 LOW): the per-step `stage_transition` alert must not make the next step wait for ntfy.

A sender that blocks until the NEXT step has started proves it: with a synchronous alert the controller sits in the first
alert and never starts step two (the wait times out); with the alert off the step's path, step two starts and releases it.
The alert is still sent before `run` returns, and an abort still rolls back before its own alert."""

from __future__ import annotations

import importlib.util
import sys
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("stage_controller_rt2", ROOT / "tools" / "stage_controller.py")
sc = importlib.util.module_from_spec(_spec)
sys.modules["stage_controller_rt2"] = sc
_spec.loader.exec_module(sc)

GO = "Don: go to stage"
SHA = "0123abcd"


class _Driver:
    def __init__(self, on_do=None):
        self.calls, self.on_do = [], on_do

    def counters(self):
        return {s: {"dropped_unauthenticated_records": 0, "dropped_refused_records": 0} for s in
                ("killswitch", "registry", "ledger")}

    def do(self, stage, step):
        self.calls.append(("do", stage, step))
        if self.on_do:
            self.on_do(stage, step)

    def check(self, stage, step):
        return []


def _controller(tmp_path, driver):
    rec = sc.Records(tmp_path / "r.jsonl")
    rec.append("alerts_proven", ok=True)
    rec.append("gate", gate="G22", ok=True)
    rec.append("gate", gate="G21", ok=True)
    return sc.Controller(rec, driver, estate="gb10", env={}, expected_services=("killswitch", "registry", "ledger"))


@pytest.fixture()
def blocking_sender(monkeypatch):
    """Replaces the stage_transition sender: it waits (up to 3 s) for the second step to start."""
    second_started = threading.Event()
    seen = {"waited_ok": [], "calls": 0}

    def sender(*, estate, env, subject, detail, **kw):
        seen["calls"] += 1
        seen["waited_ok"].append(second_started.wait(3))

    monkeypatch.setattr(sc.alert_senders, "stage_transition", sender)
    return second_started, seen


def test_the_next_step_starts_while_the_previous_steps_alert_is_still_in_flight(tmp_path, blocking_sender):
    second_started, seen = blocking_sender
    steps = sc.STAGES[1].steps
    driver = _Driver(on_do=lambda stage, step: second_started.set() if step == steps[1] else None)
    t0 = time.monotonic()
    result = _controller(tmp_path, driver).run(1, go_sentence=GO, live=True)
    assert result.status == "completed" and result.steps_done == list(steps)
    assert seen["calls"] == len(steps)                       # every alert was still sent before run returned
    assert seen["waited_ok"][0] is True                      # alert one was released by step two starting
    assert time.monotonic() - t0 < 2.5                       # no alert held the stage for its 3 s wait


def test_every_transition_alert_is_delivered_before_run_returns(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(sc.alert_senders, "stage_transition",
                        lambda *, estate, env, subject, detail, **kw: (time.sleep(0.05), sent.append(detail)))
    result = _controller(tmp_path, _Driver()).run(1, go_sentence=GO, live=True)
    assert sorted(sent) == sorted(f"{s} done" for s in result.steps_done) and len(sent) == len(sc.STAGES[1].steps)


def test_an_aborting_stage_rolls_back_before_the_aborted_alert_and_after_the_transition_alerts(tmp_path, monkeypatch):
    order = []
    rollback_started = threading.Event()
    steps = sc.STAGES[1].steps

    def slow_transition(*, estate, env, subject, detail, **kw):
        rollback_started.wait(3)                 # still in flight while the rollback runs
        time.sleep(0.3)
        order.append("transition")

    monkeypatch.setattr(sc.alert_senders, "stage_transition", slow_transition)
    monkeypatch.setattr(sc.alert_senders, "stage_aborted",
                        lambda *, estate, env, subject, detail, **kw: order.append("aborted"))
    rollback_first = sc.STAGES[1].rollback[0]

    class Failing(_Driver):
        def check(self, stage, step):
            return ["canary_c0_failed"] if step == steps[1] else []

        def do(self, stage, step):
            order.append(f"do:{step}")
            if step == rollback_first:
                rollback_started.set()
            super().do(stage, step)

    result = _controller(tmp_path, Failing()).run(1, go_sentence=GO, live=True)
    assert result.status == "aborted_rolled_back"
    assert order.index(f"do:{rollback_first}") < order.index("transition")            # the rollback did not wait for it
    assert order[-2:] == ["transition", "aborted"]                                    # ...and the aborted alert came after it


def test_a_sender_that_raises_in_the_background_is_swallowed(tmp_path, monkeypatch):
    def boom(**kw):
        raise RuntimeError("a driver bug in a sender")

    escaped = []
    monkeypatch.setattr(threading, "excepthook", lambda args: escaped.append(args.exc_type))
    monkeypatch.setattr(sc.alert_senders, "stage_transition", boom)
    result = _controller(tmp_path, _Driver()).run(1, go_sentence=GO, live=True)
    assert result.status == "completed"
    assert escaped == []                                   # nothing escaped the background thread either
