"""Backlog B16: pooled clients between services expire an idle connection before the server's keep-alive closes it,
and an idempotent GET on a connection that turned out to be dead is sent exactly once more. Nothing else is
retried: not a timeout, not a refused connection, not an HTTP answer, not a POST. Every value is made up."""
from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest

from field_core import http as fh
from field_core.clients import (LedgerClient, LedgerUnreachableError, RegistryClient,
                                RegistryUnreachableError)

REPO = Path(__file__).resolve().parents[3]
AGENT = {"agent_id": "b16-agent", "status": "active"}


# --- the numbers ---------------------------------------------------------------------------------------------------

def test_the_client_expiry_is_strictly_below_the_server_keep_alive():
    assert fh.CLIENT_KEEPALIVE_EXPIRY_S < fh.SERVER_KEEP_ALIVE_S
    assert fh.pooled_limits().keepalive_expiry == fh.CLIENT_KEEPALIVE_EXPIRY_S == 2.0


def test_server_keep_alive_is_uvicorns_default():
    uvicorn_config = pytest.importorskip("uvicorn.config")
    import inspect
    default = inspect.signature(uvicorn_config.Config).parameters["timeout_keep_alive"].default
    assert float(default) == fh.SERVER_KEEP_ALIVE_S


def test_no_service_serves_with_another_keep_alive():
    """SERVER_KEEP_ALIVE_S is true only while every service's ``uvicorn.run`` keeps the default. A service that sets
    ``timeout_keep_alive`` must keep it above CLIENT_KEEPALIVE_EXPIRY_S; change this test and the constant together."""
    if not (REPO / "services").is_dir():
        pytest.skip("not a full repo checkout")
    setters = [p.relative_to(REPO).as_posix() for p in REPO.glob("services/*/src/**/*.py")
               if "timeout_keep_alive" in p.read_text(encoding="utf-8")]
    assert setters == [], setters


def test_the_pool_sizes_stay_httpxs_defaults():
    lim, default = fh.pooled_limits(), httpx.Limits(max_connections=100, max_keepalive_connections=20)
    assert (lim.max_connections, lim.max_keepalive_connections) == (default.max_connections,
                                                                     default.max_keepalive_connections)


@pytest.mark.parametrize("cls", [RegistryClient, LedgerClient])
def test_the_shared_clients_build_their_pool_with_the_short_expiry(monkeypatch, cls):
    seen = {}

    def recorder(**kw):
        seen.update(kw)
        return object()

    monkeypatch.setattr(httpx, "Client", recorder)
    cls(base_url="http://127.0.0.1:9")
    assert seen["limits"].keepalive_expiry == fh.CLIENT_KEEPALIVE_EXPIRY_S


def test_the_sentinel_clients_build_their_pool_with_the_short_expiry(monkeypatch):
    engine = pytest.importorskip("conformance_sentinel.engine")
    for cls in (engine.SpendStatusClient, engine.DelegationIntrospectClient):
        seen = {}
        monkeypatch.setattr(httpx, "Client", lambda **kw: seen.update(kw) or object())
        cls(base_url="http://127.0.0.1:9")
        assert seen["limits"].keepalive_expiry == fh.CLIENT_KEEPALIVE_EXPIRY_S, cls


# --- get_retrying_once ---------------------------------------------------------------------------------------------

def _client(*outcomes):
    """A real httpx.Client over a MockTransport: each request takes the next outcome (an exception or a status)."""
    seen = []

    def handler(request):
        seen.append(request.method)
        out = outcomes[len(seen) - 1]
        if isinstance(out, BaseException):
            raise out
        return httpx.Response(out, json=AGENT if out == 200 else {"detail": "x"})

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


STALE = [httpx.RemoteProtocolError("Server disconnected without sending a response."),
         httpx.ReadError("[Errno 104] Connection reset by peer"),
         httpx.WriteError("[Errno 32] Broken pipe")]
NOT_STALE = [httpx.ConnectError("refused"), httpx.ReadTimeout("slow"), httpx.ConnectTimeout("slow"),
             httpx.PoolTimeout("full")]


@pytest.mark.parametrize("exc", STALE, ids=["remote-protocol", "read-reset", "write-pipe"])
def test_a_dead_connection_is_retried_exactly_once(exc):
    c, seen = _client(exc, 200)
    assert fh.get_retrying_once(c, "http://h/agents/x").status_code == 200
    assert seen == ["GET", "GET"]


@pytest.mark.parametrize("exc", STALE, ids=["remote-protocol", "read-reset", "write-pipe"])
def test_a_second_dead_connection_is_raised_not_retried_again(exc):
    c, seen = _client(exc, exc, 200)
    with pytest.raises(type(exc)):
        fh.get_retrying_once(c, "http://h/agents/x")
    assert seen == ["GET", "GET"]


@pytest.mark.parametrize("exc", NOT_STALE, ids=["connect", "read-timeout", "connect-timeout", "pool-timeout"])
def test_other_transport_errors_are_not_retried(exc):
    c, seen = _client(exc, 200)
    with pytest.raises(type(exc)):
        fh.get_retrying_once(c, "http://h/agents/x")
    assert seen == ["GET"]


@pytest.mark.parametrize("status", [404, 500, 502, 503])
def test_an_http_answer_is_never_retried(status):
    c, seen = _client(status, 200)
    assert fh.get_retrying_once(c, "http://h/agents/x").status_code == status
    assert seen == ["GET"]


def test_the_kwargs_reach_both_attempts():
    got = []

    class Stub:
        def get(self, url, **kw):
            got.append((url, kw))
            if len(got) == 1:
                raise httpx.RemoteProtocolError("closed")
            return "ok"

    assert fh.get_retrying_once(Stub(), "u", params={"a": "1"}, headers={"h": "v"}) == "ok"
    assert got == [("u", {"params": {"a": "1"}, "headers": {"h": "v"}})] * 2


# --- through the shared clients ------------------------------------------------------------------------------------

@pytest.mark.parametrize("exc", STALE, ids=["remote-protocol", "read-reset", "write-pipe"])
def test_registry_get_agent_survives_one_dead_connection(exc):
    c, seen = _client(exc, 200)
    assert RegistryClient(client=c, base_url="http://h").get_agent("b16-agent")["status"] == "active"
    assert seen == ["GET", "GET"]


def test_registry_get_agent_raises_unreachable_after_two_dead_connections():
    c, seen = _client(STALE[0], STALE[0])
    with pytest.raises(RegistryUnreachableError):
        RegistryClient(client=c, base_url="http://h").get_agent("b16-agent")
    assert seen == ["GET", "GET"]


def test_registry_list_agents_is_retried_once():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if len(seen) == 1:
            raise httpx.RemoteProtocolError("closed")
        return httpx.Response(200, json=[AGENT])

    c = httpx.Client(transport=httpx.MockTransport(handler))
    assert RegistryClient(client=c, base_url="http://h").list_agents() == [AGENT]
    assert seen == ["/agents", "/agents"]


def test_registry_patch_is_never_retried():
    c, seen = _client(STALE[0], 200)
    with pytest.raises(RegistryUnreachableError):
        RegistryClient(client=c, base_url="http://h").set_status("b16-agent", "retired")
    assert seen == ["PATCH"]


@pytest.mark.parametrize("method,path,answer", [("events", "/events", []),
                                                ("retention_check", "/retention/check", {"ok": True})])
def test_ledger_reads_are_retried_once(method, path, answer):
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if len(seen) == 1:
            raise httpx.ReadError("reset")
        return httpx.Response(200, json=answer)

    c = httpx.Client(transport=httpx.MockTransport(handler))
    assert getattr(LedgerClient(client=c, base_url="http://h"), method)() == answer
    assert seen == [path, path]


def test_ledger_append_is_never_retried():
    c, seen = _client(STALE[0], 201)
    with pytest.raises(LedgerUnreachableError):
        LedgerClient(client=c, base_url="http://h").append("b16.test", {"n": 1})
    assert seen == ["POST"]


def test_the_retry_lives_in_one_helper():
    """Every retried GET in the shared clients goes through get_retrying_once; no client grows its own loop."""
    src = (REPO / "packages/field-core/src/field_core/clients.py").read_text(encoding="utf-8") \
        if (REPO / "packages").is_dir() else ""
    if not src:
        pytest.skip("not a full repo checkout")
    assert len(re.findall(r"get_retrying_once\(self\._client", src)) == 4
    assert "for attempt" not in src
