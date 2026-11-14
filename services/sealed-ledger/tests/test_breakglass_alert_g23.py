"""G23: the ledger's operator observer raises one ntfy alert for each break-glass row it writes, and
`GET /health` carries the alert counters. A local HTTP server stands in for ntfy; the topic is FAKE."""

from __future__ import annotations

import http.server
import threading

import pytest
from fastapi.testclient import TestClient

from field_core import alert_senders, alerts
from sealed_ledger import operator_observer as obs
from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore

FAKE_TOPIC = "faketopic_unit_test_only_xyz"


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


def _env(ntfy):
    return {alerts.ENV_TOPIC: FAKE_TOPIC, alerts.ENV_BASE_URL: ntfy.base, alert_senders.ENV_ESTATE: "gb10"}


def _health(auth, attempt):
    return {"ok": True, "operator_mode": "log-only", "operator_registry_sha256_prefix": "0123456789abcdef",
            "operator_registry_rows": 4, "operator_registry_generation": 1,
            "breakglass_auth_count": auth, "breakglass_attempt_count": attempt}


class Recorder:
    def __init__(self):
        self.events = []
        self.fail = set()

    def __call__(self, event_type, payload):
        if event_type in self.fail:
            raise RuntimeError("ledger busy (simulated)")
        self.events.append((event_type, payload))


def _observer(rec, answers, env):
    return obs.OperatorObserver(
        append=rec, self_health=lambda: _health(None, None) | {"breakglass_auth_count": None},
        targets=[("kill-switch", "http://killswitch")],
        fetch=lambda url: answers.get(url.removesuffix("/health")),
        alert=lambda event_type, payload: alert_senders.alert_for_event(event_type, payload, env=env,
                                                                         sleep=lambda s: None, timeout_s=2.0))


def test_one_alert_for_each_breakglass_row_and_none_for_an_unchanged_reading(ntfy):
    rec, answers = Recorder(), {"http://killswitch": _health(0, 0)}
    o = _observer(rec, answers, _env(ntfy))
    o.observe_once()                                    # zero at startup: no row, no alert
    assert ntfy.requests == []
    answers["http://killswitch"] = _health(0, 1)        # a tried use
    o.observe_once()
    o.observe_once()                                    # the same reading again: no row, no alert
    assert len(ntfy.requests) == 1
    req = ntfy.requests[0]
    assert req["headers"]["Title"] == alerts.CLASSES["breakglass_used"].title
    assert req["headers"]["Priority"] == "5"
    assert "kill-switch" in req["body"] and "gb10" in req["body"] and "attempt 1" in req["body"]
    answers["http://killswitch"] = _health(1, 1)        # an authenticated use
    o.observe_once()
    assert len(ntfy.requests) == 2
    assert [e for e, _ in rec.events].count(obs.BREAKGLASS_EVENT) == 2


def test_a_row_that_failed_to_write_alerts_once_when_the_retry_writes_it(ntfy):
    rec, answers = Recorder(), {"http://killswitch": _health(1, 0)}
    o = _observer(rec, answers, _env(ntfy))
    rec.fail.add(obs.BREAKGLASS_EVENT)
    o.observe_once()
    assert ntfy.requests == [] and [e for e, _ in rec.events].count(obs.BREAKGLASS_EVENT) == 0
    rec.fail.clear()
    o.observe_once()
    o.observe_once()
    assert len(ntfy.requests) == 1


def test_an_alert_that_cannot_be_sent_is_counted_and_does_not_stop_the_row(ntfy):
    rec, answers = Recorder(), {"http://killswitch": _health(0, 1)}
    o = _observer(rec, answers, {})                      # no topic configured
    assert o.observe_once() >= 1
    assert [e for e, _ in rec.events].count(obs.BREAKGLASS_EVENT) == 1
    h = alerts.health_fields({})
    assert h["alerts_failed"] == 1 and h["alerts_last_failure_class"] == "breakglass_used"


def test_a_raising_alert_callback_is_caught_and_the_observer_goes_on():
    rec, answers = Recorder(), {"http://killswitch": _health(0, 1)}

    def boom(event_type, payload):
        raise RuntimeError("callback bug")

    o = obs.OperatorObserver(append=rec, self_health=lambda: {"ok": True},
                             targets=[("kill-switch", "http://killswitch")],
                             fetch=lambda url: answers.get(url.removesuffix("/health")), alert=boom)
    assert o.observe_once() >= 1
    assert [e for e, _ in rec.events].count(obs.BREAKGLASS_EVENT) == 1


def test_without_an_alert_callback_nothing_is_sent_and_nothing_breaks():
    rec = Recorder()
    o = obs.OperatorObserver(append=rec, self_health=lambda: {"ok": True},
                             targets=[("kill-switch", "http://killswitch")],
                             fetch=lambda url: _health(0, 1))
    assert o.observe_once() >= 1


def test_from_env_arms_the_alert_callback(ntfy):
    rec = Recorder()
    environ = {obs.EVERY_ENV: "60", obs.HEALTH_ENV: "kill-switch=http://killswitch", **_env(ntfy)}
    o, every = obs.from_env(environ,
                            append=rec, self_health=lambda: {"ok": True}, fetch=lambda url: _health(0, 1))
    assert o is not None and o.alert is not None and every == 60
    o.observe_once()
    assert [e for e, _ in rec.events].count(obs.BREAKGLASS_EVENT) == 1
    assert len(ntfy.requests) == 1 and ntfy.requests[0]["headers"]["Priority"] == "5"


def test_health_carries_the_alert_counters_and_never_the_topic(tmp_path, ntfy):
    client = TestClient(create_app(store=LedgerStore(tmp_path / "events.jsonl")))
    h = client.get("/health").json()
    for key in ("alerts_channel", "alerts_configured", "alerts_config_error", "alerts_sent", "alerts_failed",
                "alerts_content_withheld", "alerts_last_failure_reason", "alerts_last_failure_class",
                "alerts_last_failure_at", "alerts_last_success_at"):
        assert key in h, key
    assert h["alerts_channel"] == "ntfy" and h["alerts_failed"] == 0
    alert_senders.breakglass_used(subject="kill-switch", estate="gb10", env={})   # not configured: counted
    h = client.get("/health").json()
    assert h["alerts_failed"] == 1 and h["alerts_last_failure_class"] == "breakglass_used"
    assert FAKE_TOPIC not in client.get("/health").text
