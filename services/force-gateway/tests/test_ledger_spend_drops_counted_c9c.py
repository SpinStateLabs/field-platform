"""Audit-ledger appends and spend forwards that fail are no longer silent (scout note,
pattern of the registry/federation drop counters). `_ledger_event` and `_meter_usage` ended in
a bare `except Exception: pass`: a lost gateway.* audit event or a lost /usage report left no
log, no counter and no trace in /health. Now each drop is counted (`ledger_appends_dropped`,
`spend_forwards_dropped`), logged (exception TYPE only) and shown in /health. Traffic is
unchanged: the response is the same with a broken ledger or governor."""
from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from force_gateway.api import create_app, mock_upstream

MARK = "zz-marker-do-not-echo"
AGENT = {"x-field-agent-id": "invoicing-agent"}
BODY = {"model": "m", "messages": []}


class _Resp:
    status_code = 201


class _Governor:
    def __init__(self, raises=None, status=201):
        self.raises, self.status, self.calls = raises, status, []

    def post(self, url, json=None, **kw):
        self.calls.append(url)
        if self.raises is not None:
            raise self.raises
        r = _Resp()
        r.status_code = self.status
        return r


class _Ledger:
    def __init__(self, raises=None):
        self.raises, self.events = raises, []

    def append(self, event_type, payload=None, agent_id=None):
        if self.raises is not None:
            raise self.raises
        self.events.append(event_type)


def _client(**kw):
    return TestClient(create_app(upstream=mock_upstream, **kw))


def _health(c):
    return c.get("/health").json()


def _ledger_trigger(c):
    # an unknown preset-less call that ledgers nothing; use the bypass route's ledger path
    # via the module helper so the test does not depend on a route's policy.
    from force_gateway.api import _ledger_event
    _ledger_event(c.app, "gateway.test", {"k": 1})


def test_failed_ledger_append_is_counted():
    c = _client(ledger_client=_Ledger(raises=ConnectionError(MARK)))
    assert _health(c)["ledger_appends_dropped"] == 0
    _ledger_trigger(c)
    _ledger_trigger(c)
    assert _health(c)["ledger_appends_dropped"] == 2


def test_working_or_absent_ledger_counts_nothing():
    for led in (None, _Ledger()):
        c = _client(ledger_client=led)
        _ledger_trigger(c)
        assert _health(c)["ledger_appends_dropped"] == 0


def test_failed_spend_forward_is_counted_and_traffic_is_unchanged():
    ok = _client(governor_client=_Governor()).post("/v1/messages", json=BODY, headers=AGENT)
    c = _client(governor_client=_Governor(raises=TimeoutError(MARK)))
    assert _health(c)["spend_forwards_dropped"] == 0
    r = c.post("/v1/messages", json=BODY, headers=AGENT)
    assert (r.status_code, r.json()) == (ok.status_code, ok.json())
    assert _health(c)["spend_forwards_dropped"] == 1


def test_failed_spend_fallback_is_counted():
    g = _Governor(status=404)
    c = _client(governor_client=g)
    g.raises = None
    orig = g.post

    def post(url, json=None, **kw):
        if url == "/spend":
            raise OSError(MARK)
        return orig(url, json=json, **kw)
    g.post = post
    c.post("/v1/messages", json=BODY, headers=AGENT)
    assert _health(c)["spend_forwards_dropped"] == 1


def test_working_governor_counts_nothing():
    c = _client(governor_client=_Governor())
    c.post("/v1/messages", json=BODY, headers=AGENT)
    assert _health(c)["spend_forwards_dropped"] == 0


def test_drops_are_logged_with_the_exception_type_never_the_message(caplog):
    c = _client(ledger_client=_Ledger(raises=ConnectionError(MARK)),
                governor_client=_Governor(raises=TimeoutError(MARK)))
    with caplog.at_level(logging.WARNING, logger="force_gateway"):
        _ledger_trigger(c)
        c.post("/v1/messages", json=BODY, headers=AGENT)
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "ConnectionError" in text and "TimeoutError" in text and "dropped" in text
    assert "gateway.test" in text
    assert MARK not in text


def test_health_keeps_its_existing_fields():
    h = _health(_client())
    for key in ("ok", "service", "version", "mock", "judge", "enforce", "build_sha"):
        assert key in h
