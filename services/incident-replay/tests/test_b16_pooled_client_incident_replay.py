"""Backlog B16 follow-up: incident-replay's LedgerQueryClient and TokenQueryClient build their pools with
field_core.http.pooled_limits() (keepalive_expiry 2 s, below uvicorn's 5 s keep-alive), and every one of their GETs
is sent once more on a dead pooled connection only. A timeout or a refused connection is never retried. Every value
is made up."""
from __future__ import annotations

import httpx
import pytest

from field_core.http import CLIENT_KEEPALIVE_EXPIRY_S
from incident_replay.engine import LedgerQueryClient, TokenQueryClient


@pytest.mark.parametrize("cls", [LedgerQueryClient, TokenQueryClient])
def test_the_client_has_the_short_keepalive_expiry(monkeypatch, cls):
    built = []
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: built.append(kw) or object())
    cls(base_url="http://h")
    assert len(built) == 1 and built[0]["limits"].keepalive_expiry == CLIENT_KEEPALIVE_EXPIRY_S


class Flaky:
    def __init__(self, errors, body):
        self.errors, self.body, self.urls = list(errors), body, []

    def get(self, url, **kw):
        self.urls.append(url)
        if self.errors:
            raise self.errors.pop(0)
        return httpx.Response(200, json=self.body, request=httpx.Request("GET", url))


@pytest.mark.parametrize("call,path,body", [
    (lambda c: LedgerQueryClient(client=c, base_url="http://h").events(), "/events", []),
    (lambda c: LedgerQueryClient(client=c, base_url="http://h").verify(), "/verify", {"ok": True, "length": 1}),
    (lambda c: LedgerQueryClient(client=c, base_url="http://h").health(), "/health", {"ok": True}),
    (lambda c: TokenQueryClient(client=c, base_url="http://h").tokens("a"), "/tokens", []),
], ids=["events", "verify", "health", "tokens"])
def test_each_get_is_sent_once_more_on_a_dead_connection(call, path, body):
    c = Flaky([httpx.RemoteProtocolError("closed")], body)
    assert call(c) == body
    assert c.urls == [f"http://h{path}"] * 2


@pytest.mark.parametrize("exc", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")],
                         ids=["connect", "timeout"])
def test_a_refused_or_timed_out_get_is_not_retried(exc):
    c = Flaky([exc], [])
    with pytest.raises(type(exc)):
        LedgerQueryClient(client=c, base_url="http://h").events()
    assert len(c.urls) == 1
