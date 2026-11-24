"""The SDK's default HTTP clients ignore the proxy environment, do not follow redirects, and keep their timeouts (S12-8)."""
from __future__ import annotations

import http.server
import threading

import httpx
import pytest

from field_agent.agent import FieldAgent
from field_agent.bootstrap import _client as bootstrap_client
from field_agent.federation import FederationClient
from field_agent.liveness import LivenessClient
from field_agent.usage import UsageClient

SECRET = "s12-8-test-secret"


class _Fake(http.server.BaseHTTPRequestHandler):
    seen: list = []

    def do_GET(self):
        _Fake.seen.append((self.path, self.headers.get("x-field-auth")))
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/landed")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        body = b"{}"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture()
def fake(monkeypatch):
    _Fake.seen = []
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    for v in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        monkeypatch.setenv(v, "http://127.0.0.1:9")          # a closed port: any proxy hop fails
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def _wrapped():
    return {
        "usage": (UsageClient()._client, 5.0),
        "liveness": (LivenessClient()._client, 5.0),
        "federation": (FederationClient()._client, 10.0),
        "bootstrap": (bootstrap_client(None), 5.0),
        "agent-sentinel": (FieldAgent("a")._sentinel._client, 10.0),
    }


@pytest.mark.parametrize("name", ["usage", "liveness", "federation", "bootstrap", "agent-sentinel"])
def test_default_client_reaches_the_server_directly_with_the_secret(fake, name):
    client, _ = _wrapped()[name]
    assert client.get(fake + "/ok").status_code == 200
    assert _Fake.seen == [("/ok", SECRET)]


@pytest.mark.parametrize("name", ["usage", "liveness", "federation", "bootstrap", "agent-sentinel"])
def test_default_client_does_not_follow_a_redirect(fake, name):
    client, _ = _wrapped()[name]
    assert client.get(fake + "/redirect").status_code == 302
    assert [p for p, _ in _Fake.seen] == ["/redirect"]


@pytest.mark.parametrize("name,timeout", [("usage", 5.0), ("liveness", 5.0), ("federation", 10.0),
                                          ("bootstrap", 5.0), ("agent-sentinel", 10.0)])
def test_default_client_keeps_its_timeout(fake, name, timeout):
    inner = _wrapped()[name][0]._inner
    assert inner.trust_env is False and inner.follow_redirects is False
    assert inner.timeout == httpx.Timeout(timeout)


def test_an_injected_client_is_used_untouched():
    mine = httpx.Client()
    assert UsageClient(client=mine)._client._inner is mine
    assert LivenessClient(client=mine)._client._inner is mine
    assert FederationClient(client=mine)._client._inner is mine
    assert bootstrap_client(mine)._inner is mine
