"""Backlog B16 follow-up: the console's ServiceClient builds its pool with field_core.http.pooled_limits()
(keepalive_expiry 2 s, below uvicorn's 5 s keep-alive); its GET is sent once more on a dead pooled connection only,
and its POST never is. Failures still come back as (0, class name). Every value is made up."""
from __future__ import annotations

import httpx
import pytest

from field_core.http import CLIENT_KEEPALIVE_EXPIRY_S
from ops_console.api import ServiceClient


def test_the_service_client_has_the_short_keepalive_expiry(monkeypatch):
    built = []
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: built.append(kw) or object())
    ServiceClient(base_url="http://registry:8001")
    assert len(built) == 1 and built[0]["limits"].keepalive_expiry == CLIENT_KEEPALIVE_EXPIRY_S


class Flaky:
    def __init__(self, errors):
        self.errors, self.calls = list(errors), []

    def _go(self, method, path):
        self.calls.append(method)
        if self.errors:
            raise self.errors.pop(0)
        return httpx.Response(200, json={"ok": True}, request=httpx.Request(method, "http://h" + path))

    def get(self, path, **kw):
        return self._go("GET", path)

    def post(self, path, **kw):
        return self._go("POST", path)


def test_a_get_on_a_dead_connection_is_sent_once_more():
    c = Flaky([httpx.RemoteProtocolError("closed")])
    assert ServiceClient(client=c, base_url="http://h").get("/agents") == (200, {"ok": True})
    assert c.calls == ["GET", "GET"]


def test_two_dead_connections_are_still_a_graceful_failure():
    c = Flaky([httpx.ReadError("reset"), httpx.ReadError("reset")])
    assert ServiceClient(client=c, base_url="http://h").get("/agents") == (0, "ReadError")
    assert c.calls == ["GET", "GET"]


@pytest.mark.parametrize("exc", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")],
                         ids=["connect", "timeout"])
def test_a_refused_or_timed_out_get_is_not_retried(exc):
    c = Flaky([exc])
    assert ServiceClient(client=c, base_url="http://h").get("/agents") == (0, type(exc).__name__)
    assert c.calls == ["GET"]


def test_a_post_is_never_retried():
    c = Flaky([httpx.RemoteProtocolError("closed")])
    assert ServiceClient(client=c, base_url="http://h").post("/check", json={}) == (0, "RemoteProtocolError")
    assert c.calls == ["POST"]
