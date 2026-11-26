"""Backlog B16 follow-up: the @governed SDK's Governor builds its pool with field_core.http.pooled_limits()
(keepalive_expiry 2 s, below uvicorn's 5 s keep-alive). Its one call, POST /check, is never retried: a dead
connection still fails closed as ActionBlocked. Every value is made up."""
from __future__ import annotations

import httpx
import pytest

import conformance_sentinel.governed as g
from conformance_sentinel.governed import ActionBlocked, Governor
from field_core.http import CLIENT_KEEPALIVE_EXPIRY_S


def test_the_governor_client_has_the_short_keepalive_expiry(monkeypatch):
    built = []
    monkeypatch.setattr(g.httpx, "Client", lambda *a, **kw: built.append(kw) or object())
    Governor(agent_id="b16-agent", sentinel_url="http://sentinel:8004")
    assert len(built) == 1 and built[0]["limits"].keepalive_expiry == CLIENT_KEEPALIVE_EXPIRY_S


def test_post_check_on_a_dead_connection_is_not_retried_and_fails_closed():
    calls = []

    class Dead:
        def post(self, url, **kw):
            calls.append(url)
            raise httpx.RemoteProtocolError("closed")

    with pytest.raises(ActionBlocked):
        Governor(agent_id="b16-agent", sentinel_url="http://sentinel:8004", client=Dead()).check("act")
    assert calls == ["http://sentinel:8004/check"]
