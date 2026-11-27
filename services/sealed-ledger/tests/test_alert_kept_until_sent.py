"""The operator observer keeps an alert until a send is confirmed.

A failed send (a result that is not ok, or a raise) leaves the alert waiting; it is sent again after a wait that grows
to a cap; it leaves the queue only on a confirmed send; it survives a restart when FIELD_DATA_DIR is set.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from field_core import alert_senders, alerts
from sealed_ledger import operator_observer as obs
from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore


def _health(auth, attempt):
    return {"ok": True, "operator_mode": "log-only", "operator_registry_sha256_prefix": "0123456789abcdef",
            "operator_registry_rows": 4, "operator_registry_generation": 1,
            "breakglass_auth_count": auth, "breakglass_attempt_count": attempt}


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class Sender:
    """Answers from ``answers`` in order, then confirms; records what it was asked to send."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.sent = []

    def __call__(self, event_type, payload):
        self.sent.append((payload["service"], payload["breakglass_attempt_count"]))
        answer = self.answers.pop(0) if self.answers else alerts.AlertResult(True, "breakglass_used", 1)
        if isinstance(answer, Exception):
            raise answer
        return answer


FAILED = alerts.AlertResult(False, "breakglass_used", 3, "unreachable")


def _observer(readings, sender, clock, **kw):
    return obs.OperatorObserver(
        append=lambda event_type, payload: None,
        self_health=lambda: _health(None, None) | {"breakglass_auth_count": None},
        targets=[(name, f"http://{name}") for name in readings],
        fetch=lambda url: readings.get(url.removesuffix("/health").removeprefix("http://")),
        alert=sender, clock=clock, **kw)


@pytest.mark.parametrize("failure", [FAILED, RuntimeError("sender bug"), False, object()],
                         ids=["not-ok-result", "raises", "false", "no-ok-attribute"])
def test_a_send_that_is_not_confirmed_keeps_the_alert_and_it_is_sent_again(failure):
    readings, clock, sender = {"a": _health(0, 1)}, Clock(), Sender(failure)
    o = _observer(readings, sender, clock)
    o.observe_once()
    assert sender.sent == [("a", 1)] and o.pending_alerts() == 1
    clock.now += obs.ALERT_RETRY_FIRST_S
    o.observe_once()
    assert sender.sent == [("a", 1), ("a", 1)] and o.pending_alerts() == 0
    clock.now += obs.ALERT_RETRY_MAX_S
    o.observe_once()
    assert len(sender.sent) == 2                                  # confirmed once: never again


@pytest.mark.parametrize("confirmed", [None, True, alerts.AlertResult(True, "breakglass_used", 1)],
                         ids=["none", "true", "ok-result"])
def test_a_confirmed_send_removes_the_alert(confirmed):
    readings, clock, sender = {"a": _health(0, 1)}, Clock(), Sender(confirmed)
    o = _observer(readings, sender, clock)
    o.observe_once()
    assert o.pending_alerts() == 0 and len(sender.sent) == 1


def test_retries_wait_longer_each_time_up_to_the_cap_and_never_stop():
    readings, clock, sender = {"a": _health(0, 1)}, Clock(), Sender(*[FAILED] * 12)
    o = _observer(readings, sender, clock)
    o.observe_once()
    waits = []
    for _ in range(11):
        before, waited = len(sender.sent), 0.0
        while len(sender.sent) == before:
            clock.now += 1.0
            waited += 1.0
            o.observe_once()
            assert waited <= obs.ALERT_RETRY_MAX_S, "the alert was given up"
        waits.append(waited)
    assert waits[:5] == [30.0, 60.0, 120.0, 240.0, 480.0]
    assert set(waits[5:]) == {obs.ALERT_RETRY_MAX_S}
    assert o.pending_alerts() == 1


def test_many_ticks_before_the_wait_is_over_send_nothing_more():
    readings, clock, sender = {"a": _health(0, 1)}, Clock(), Sender(FAILED, FAILED)
    o = _observer(readings, sender, clock)
    for _ in range(50):
        o.observe_once()
    assert len(sender.sent) == 1


def test_a_newer_reading_replaces_the_waiting_one_without_shortening_the_wait():
    readings, clock, sender = {"a": _health(0, 1)}, Clock(), Sender(FAILED)
    o = _observer(readings, sender, clock)
    o.observe_once()
    for attempt in (2, 3, 4):
        readings["a"] = _health(0, attempt)
        clock.now += 1.0
        o.observe_once()
    assert len(sender.sent) == 1 and o.pending_alerts() == 1
    clock.now += obs.ALERT_RETRY_FIRST_S
    o.observe_once()
    assert sender.sent == [("a", 1), ("a", 4)] and o.pending_alerts() == 0


def test_a_failing_alert_does_not_hold_back_the_others():
    readings, clock = {"a": _health(0, 1), "b": _health(0, 1)}, Clock()
    sender = Sender(FAILED)
    o = _observer(readings, sender, clock)
    o.observe_once()
    assert sender.sent == [("a", 1), ("b", 1)] and o.pending_alerts() == 1


def test_a_reading_that_arrives_during_a_send_is_sent_too():
    readings, clock = {"a": _health(0, 1)}, Clock()
    sent = []

    def sender(event_type, payload):
        sent.append(payload["breakglass_attempt_count"])
        if len(sent) == 1:
            o._raise_alert(event_type, payload | {"breakglass_attempt_count": 2})
        return None

    o = _observer(readings, sender, clock)
    o.observe_once()
    assert sent == [1] and o.pending_alerts() == 1
    o.observe_once()
    assert sent == [1, 2] and o.pending_alerts() == 0


def test_a_tick_during_a_send_does_not_send_the_same_alert_again():
    readings, clock = {"a": _health(0, 1)}, Clock()
    sent = []

    def sender(event_type, payload):
        sent.append(payload["breakglass_attempt_count"])
        if len(sent) == 1:
            o.observe_once()                       # a second tick while this send is still running
        return None

    o = _observer(readings, sender, clock)
    o.observe_once()
    assert sent == [1] and o.pending_alerts() == 0


def test_a_waiting_alert_survives_a_restart_and_is_sent_at_once(tmp_path):
    path = tmp_path / "ledger-observer" / "pending-alerts.json"
    readings, clock = {"a": _health(0, 1)}, Clock()
    first = _observer(readings, Sender(FAILED), clock, pending_file=path)
    first.observe_once()
    assert [r["payload"]["service"] for r in json.loads(path.read_text(encoding="utf-8"))] == ["a"]
    sender = Sender()
    second = _observer({}, sender, Clock(), pending_file=path)    # the service answers nothing after the restart
    assert second.pending_alerts() == 1
    second.observe_once()
    assert sender.sent == [("a", 1)] and second.pending_alerts() == 0
    assert json.loads(path.read_text(encoding="utf-8")) == []
    third = _observer({}, Sender(), Clock(), pending_file=path)
    assert third.pending_alerts() == 0


@pytest.mark.parametrize("content", [b"", b"{", b"{}", b"[1, null]", b"\xff\xfe",
                                     b'[{"event_type": "made.up", "payload": {}}]',
                                     b'[{"event_type": "operator.breakglass_counters_changed", "payload": 3}]',
                                     b'[{"event_type": "operator.breakglass_counters_changed", '
                                     b'"payload": {"service": ["x"]}}]',
                                     b"[" * 100000],
                         ids=["empty", "cut", "object", "not-rows", "not-utf8", "unknown-type", "payload-not-object",
                              "service-not-text", "deep"])
def test_a_file_that_is_not_what_was_written_is_ignored(tmp_path, content):
    path = tmp_path / "pending-alerts.json"
    path.write_bytes(content)
    o = _observer({}, Sender(), Clock(), pending_file=path)
    assert o.pending_alerts() == 0
    o.observe_once()


def test_a_file_that_cannot_be_written_does_not_stop_the_observer(tmp_path):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    sender = Sender(FAILED)
    o = _observer({"a": _health(0, 1)}, sender, Clock(), pending_file=blocker / "pending-alerts.json")
    o.observe_once()
    assert sender.sent == [("a", 1)] and o.pending_alerts() == 1
    assert o.pending_save_failures() == 2                     # once when queued, once after the failed send


def test_saves_that_work_count_no_failure(tmp_path):
    o = _observer({"a": _health(0, 1)}, Sender(FAILED), Clock(), pending_file=tmp_path / "pending-alerts.json")
    o.observe_once()
    assert o.pending_alerts() == 1 and o.pending_save_failures() == 0


def test_ledger_health_shows_failed_saves(tmp_path):
    app = create_app(store=LedgerStore(tmp_path / "events.jsonl"))
    client = TestClient(app)
    assert client.get("/health").json()["alerts_pending_save_failures"] == 0
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("x", encoding="utf-8")
    o = _observer({"a": _health(0, 1)}, Sender(FAILED), Clock(), pending_file=blocker / "pending-alerts.json")
    o.observe_once()
    app.state.operator_observer = o
    assert client.get("/health").json()["alerts_pending_save_failures"] == 2


def test_from_env_keeps_the_file_under_the_data_directory(tmp_path):
    common = {"append": lambda e, p: None, "self_health": lambda: {"ok": True}}
    o, _ = obs.from_env({obs.EVERY_ENV: "60", "FIELD_DATA_DIR": str(tmp_path)}, **common)
    assert o.pending_file == tmp_path / "ledger-observer" / "pending-alerts.json"
    o, _ = obs.from_env({obs.EVERY_ENV: "60"}, **common)
    assert o.pending_file is None


def test_the_real_sender_with_no_channel_keeps_the_alert_and_health_counts_it():
    alerts._reset_stats()
    o = _observer({"a": _health(0, 1)},
                  lambda event_type, payload: alert_senders.alert_for_event(event_type, payload, env={}), Clock())
    o.observe_once()
    assert o.pending_alerts() == 1 and alerts.health_fields({})["alerts_failed"] == 1
    alerts._reset_stats()


def test_ledger_health_shows_how_many_alerts_wait(tmp_path):
    app = create_app(store=LedgerStore(tmp_path / "events.jsonl"))
    client = TestClient(app)
    assert client.get("/health").json()["alerts_pending"] == 0
    o = _observer({"a": _health(0, 1)}, Sender(FAILED), Clock())
    o.observe_once()
    app.state.operator_observer = o
    assert client.get("/health").json()["alerts_pending"] == 1
