"""Backlog B16 follow-up: the gateway's SentinelClient builds its pool with field_core.http.pooled_limits()
(keepalive_expiry 2 s, below uvicorn's 5 s keep-alive). Its one call, POST /check, is never retried: a dead
connection is a SentinelUnavailable (the gateway refuses 503), exactly as before. Every value is made up."""
from __future__ import annotations

import httpx
import pytest

from field_core.http import CLIENT_KEEPALIVE_EXPIRY_S
from force_gateway.api import SentinelClient, SentinelUnavailable


def test_the_sentinel_client_has_the_short_keepalive_expiry(monkeypatch):
    built = []
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: built.append(kw) or object())
    SentinelClient(base_url="http://sentinel:8004", timeout=5)
    assert len(built) == 1 and built[0]["limits"].keepalive_expiry == CLIENT_KEEPALIVE_EXPIRY_S


def test_post_check_on_a_dead_connection_is_not_retried():
    calls = []

    class Dead:
        def post(self, url, **kw):
            calls.append(url)
            raise httpx.RemoteProtocolError("closed")

    with pytest.raises(SentinelUnavailable):
        SentinelClient(client=Dead(), base_url="http://sentinel:8004", timeout=5).check("a", "t", "llm.messages")
    assert calls == ["http://sentinel:8004/check"]
