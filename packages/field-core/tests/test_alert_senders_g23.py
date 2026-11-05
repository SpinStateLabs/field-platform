"""G23: the senders for the six production alert classes and the ledger-event mapping.

Every test runs against a local HTTP server on 127.0.0.1 standing in for ntfy. Topics and tokens are FAKE values."""

from __future__ import annotations

import http.server
import threading

import pytest

from field_core import alert_senders, alerts

FAKE_TOPIC = "faketopic_unit_test_only_xyz"
FAKE_KEY = "fok_" + "A" * 43
FAKE_HASH = "ab" * 32


class _Ntfy:
    def __init__(self, status=200):
        self.requests: list[dict] = []
        outer = self

        class H(http.server.BaseHTTPRequestHandler):
            def do_POST(self):  # noqa: N802
                n = int(self.headers.get("Content-Length") or 0)
                outer.requests.append({"headers": dict(self.headers), "body": self.rfile.read(n).decode("utf-8")})
                self.send_response(status)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"{}")

            def log_message(self, *a):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def ntfy():
    s = _Ntfy()
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _clean():
    alerts._reset_stats()
    yield
    alerts._reset_stats()


def _env(ntfy, **extra):
    env = {alerts.ENV_TOPIC: FAKE_TOPIC, alerts.ENV_BASE_URL: ntfy.base}
    env.update(extra)
    return env


FAST = {"sleep": lambda s: None, "timeout_s": 2.0}
PRODUCTION = sorted(c for c in alerts.CLASSES if c != "test")


def test_there_is_one_sender_per_production_class_and_none_for_test():
    assert sorted(alert_senders.SENDERS) == PRODUCTION
    assert len(PRODUCTION) == 6


@pytest.mark.parametrize("alert_class", PRODUCTION)
def test_a_forced_condition_sends_exactly_one_alert_of_its_class(alert_class, ntfy):
    result = alert_senders.SENDERS[alert_class](subject="svc-a", detail="a fixed detail", estate="gb10",
                                                env=_env(ntfy), **FAST)
    assert result.ok and result.alert_class == alert_class and result.attempts == 1
    assert len(ntfy.requests) == 1
    req = ntfy.requests[0]
    assert req["headers"]["Title"] == alerts.CLASSES[alert_class].title
    assert req["headers"]["Priority"] == str(alerts.CLASSES[alert_class].priority)
    assert "gb10" in req["body"] and "svc-a" in req["body"]
    assert alerts.health_fields(_env(ntfy))["alerts_sent"] == 1


@pytest.mark.parametrize("alert_class", PRODUCTION)
def test_no_alert_carries_a_key_a_token_a_hash_or_the_topic(alert_class, ntfy):
    result = alert_senders.SENDERS[alert_class](subject=FAKE_KEY, detail=f"{FAKE_HASH} {FAKE_TOPIC}",
                                                estate="gb10", env=_env(ntfy), **FAST)
    assert result.ok and set(result.withheld_fields) == {"subject", "detail"}
    sent = "\n".join(f"{k}: {v}" for r in ntfy.requests for k, v in r["headers"].items()) + ntfy.requests[0]["body"]
    for secret in (FAKE_KEY, FAKE_HASH, FAKE_TOPIC):
        assert secret not in sent


@pytest.mark.parametrize("alert_class", PRODUCTION)
def test_a_missing_topic_is_counted_and_never_raised(alert_class):
    result = alert_senders.SENDERS[alert_class](subject="s", estate="gb10", env={})
    assert not result.ok and result.reason == "not_configured"
    health = alerts.health_fields({})
    assert health["alerts_failed"] == 1 and health["alerts_last_failure_class"] == alert_class


def test_a_server_error_is_counted_and_never_raised():
    bad = _Ntfy(status=500)
    try:
        result = alert_senders.breakglass_used(subject="kill-switch", estate="gb10", env=_env(bad),
                                               max_attempts=1, **FAST)
        assert not result.ok and result.reason == "http_500"
        assert alerts.health_fields(_env(bad))["alerts_failed"] == 1
    finally:
        bad.close()


def test_an_unexpected_error_inside_the_library_is_counted_and_never_raised(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("library bug")

    monkeypatch.setattr(alerts, "send", boom)
    result = alert_senders.stage_aborted(subject="s", estate="gb10", env={})
    assert not result.ok and result.reason == "sender_error_RuntimeError"
    assert alerts.health_fields({})["alerts_failed"] == 1


def test_estate_comes_from_the_env_and_is_unknown_when_unset(ntfy):
    assert alert_senders.estate_name({}) == "unknown"
    assert alert_senders.estate_name({alert_senders.ENV_ESTATE: "  "}) == "unknown"
    assert alert_senders.estate_name({alert_senders.ENV_ESTATE: " fly "}) == "fly"
    alert_senders.rotation_failed(env=_env(ntfy, **{alert_senders.ENV_ESTATE: "fly"}), **FAST)
    assert "fly" in ntfy.requests[0]["body"]


# ---------------------------------------------------------------- ledger event mapping

EVENTS = {
    "keyrotation.failed": ({"operator_id": "don", "phase": "publish", "reason_class": "verify", "reverted": True},
                           "rotation_failed", "phase publish"),
    "keyrotation.overdue": ({"operator_id": "don", "estate": "gb10", "severity": "high",
                             "overdue_reason": "near_expiry"}, "rotation_overdue", "near_expiry"),
    "keyrotation.breakglass_used": ({"estate": "gb10", "service": "kill-switch", "count": 2, "previous_count": 1},
                                    "breakglass_used", "count 2"),
    "keyrotation.breakglass_attempt": ({"estate": "gb10", "service": "kill-switch", "count": 1,
                                        "previous_count": 0}, "breakglass_used", "count 1"),
    "operator.breakglass_counters_changed": ({"service": "kill-switch", "breakglass_auth_count": 1,
                                              "breakglass_attempt_count": 2}, "breakglass_used", "auth 1, attempt 2"),
}


@pytest.mark.parametrize("event_type", sorted(EVENTS))
def test_a_ledger_event_raises_exactly_one_alert_of_its_class(event_type, ntfy):
    payload, alert_class, expected = EVENTS[event_type]
    result = alert_senders.alert_for_event(event_type, payload, estate="gb10", env=_env(ntfy), **FAST)
    assert result.ok and result.alert_class == alert_class
    assert len(ntfy.requests) == 1 and expected in ntfy.requests[0]["body"]


@pytest.mark.parametrize("event_type", ["keyrotation.started", "keyrotation.completed", "keyrotation.aborted",
                                        "keyrotation.skipped", "operator.mode_changed", "nonsense"])
def test_an_event_that_raises_no_alert_sends_nothing(event_type, ntfy):
    assert alert_senders.alert_for_event(event_type, {}, estate="gb10", env=_env(ntfy), **FAST) is None
    assert ntfy.requests == []


@pytest.mark.parametrize("payload", [None, "text", 7, [], {"service": 5, "count": object()}])
def test_a_payload_of_a_wrong_shape_still_raises_its_alert(payload, ntfy):
    result = alert_senders.alert_for_event("keyrotation.breakglass_used", payload, estate="gb10",
                                           env=_env(ntfy), **FAST)
    assert result is not None and result.ok and len(ntfy.requests) == 1


def test_every_mapped_event_type_is_a_known_event_or_the_ledger_observer_row():
    from field_core import rotation_events
    for event_type, alert_class in alert_senders.EVENT_CLASS.items():
        assert alert_class in alert_senders.SENDERS
        assert event_type in rotation_events.EVENTS or event_type == "operator.breakglass_counters_changed"


def test_there_is_no_ledger_event_for_rotation_halted_so_it_has_no_mapping():
    from field_core import rotation_events
    assert "rotation_halted" not in alert_senders.EVENT_CLASS.values()
    assert not any("halted" in e for e in rotation_events.EVENTS)
