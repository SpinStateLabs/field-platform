"""C-1182 (C-1150 F5): the clients that carry the caller pair do not read the process proxy environment.

``LedgerClient`` and ``RegistryClient`` build their own ``httpx.Client`` when none is injected. httpx reads
``HTTP_PROXY`` and friends by default (``trust_env=True``), so a request carrying ``x-field-auth`` and the signed
caller headers could be sent to whatever proxy the process environment names. Each test sets the proxy variables to a
local listener, sends one request through the client's own ``httpx.Client`` to a second local listener, and checks
which of the two saw it. Loopback addresses only; no estate value, no key.
"""
from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from field_core.clients import LedgerClient, RegistryClient

PROXY_VARS = ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY", "all_proxy")
NO_PROXY_VARS = ("NO_PROXY", "no_proxy")


class _Counter(BaseHTTPRequestHandler):
    seen: list[str]

    def do_GET(self):  # noqa: N802 - http.server's name
        self.server.seen.append(self.path)
        body = b"{}"
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # silence the test output
        pass


@pytest.fixture()
def two_listeners():
    servers = []
    for _ in range(2):
        srv = HTTPServer(("127.0.0.1", 0), _Counter)
        srv.seen = []
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
    yield servers
    for srv in servers:
        srv.shutdown()
        srv.server_close()


@pytest.fixture()
def proxy_env(monkeypatch, two_listeners):
    proxy, target = two_listeners
    for name in NO_PROXY_VARS:
        monkeypatch.delenv(name, raising=False)
    for name in PROXY_VARS:
        monkeypatch.setenv(name, f"http://127.0.0.1:{proxy.server_port}")
    return proxy, target


def _send(client_cls, target):
    base = f"http://127.0.0.1:{target.server_port}"
    client = client_cls(base_url=base)
    try:
        return client._client.get(f"{base}/probe")
    finally:
        client._client.close()


@pytest.mark.parametrize("client_cls", [LedgerClient, RegistryClient])
def test_a_client_built_here_ignores_the_proxy_environment(client_cls, proxy_env):
    proxy, target = proxy_env
    assert _send(client_cls, target).status_code == 200
    assert target.seen == ["/probe"], "the request must go straight to the target"
    assert proxy.seen == [], "no request may go via the proxy named in the environment"


@pytest.mark.parametrize("client_cls", [LedgerClient, RegistryClient])
def test_the_client_is_pinned_not_just_unset(client_cls, proxy_env):
    """trust_env is False on the client object itself, so a later change of the environment cannot turn it on."""
    _, target = proxy_env
    client = client_cls(base_url=f"http://127.0.0.1:{target.server_port}")
    try:
        assert client._client.trust_env is False
    finally:
        client._client.close()
