"""Backlog B16 follow-up: engine_from_env builds every upstream client with field_core.http.pooled_limits()
(keepalive_expiry 2 s, below uvicorn's 5 s keep-alive), and a metric fetch (a GET) is sent once more on a dead
pooled connection only. A timeout or a refused connection is never retried. Every value is made up."""
from __future__ import annotations

import httpx
import pytest

from attestation_reporter import engine as eng
from attestation_reporter.api import UPSTREAMS, engine_from_env
from field_core.http import CLIENT_KEEPALIVE_EXPIRY_S


def test_every_upstream_client_has_the_short_keepalive_expiry(monkeypatch):
    built = []
    monkeypatch.setattr(httpx, "Client", lambda *a, **kw: built.append(kw) or object())
    engine_from_env(org="Acme")
    assert len(built) == len(UPSTREAMS)
    assert all(kw["limits"].keepalive_expiry == CLIENT_KEEPALIVE_EXPIRY_S for kw in built)


class Flaky:
    def __init__(self, errors, answer):
        self.errors, self.answer, self.calls = list(errors), answer, 0

    def get(self, url, **kw):
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return self.answer


ANSWER = httpx.Response(200, json={"n": 1}, request=httpx.Request("GET", "http://h/x"))


@pytest.mark.parametrize("exc", [httpx.RemoteProtocolError("closed"), httpx.ReadError("reset"),
                                 httpx.WriteError("pipe")], ids=["remote-protocol", "read", "write"])
def test_a_fetch_on_a_dead_connection_is_sent_once_more(exc):
    c = Flaky([exc], ANSWER)
    data, query, ok, status = eng._fetch_answer(c, "http://ledger", "/events")
    assert (data, ok, status, c.calls) == ({"n": 1}, True, 200, 2)
    assert query == "GET http://ledger/events"


@pytest.mark.parametrize("exc", [httpx.ConnectError("refused"), httpx.ReadTimeout("slow")],
                         ids=["connect", "timeout"])
def test_a_refused_or_timed_out_fetch_is_not_retried(exc):
    c = Flaky([exc], ANSWER)
    assert eng._fetch_answer(c, "http://ledger", "/events")[2] is False
    assert c.calls == 1


def test_two_dead_connections_are_an_unreachable_upstream():
    c = Flaky([httpx.RemoteProtocolError("a"), httpx.RemoteProtocolError("b")], ANSWER)
    assert eng._fetch_answer(c, "http://ledger", "/events")[2:] == (False, None)
    assert c.calls == 2
