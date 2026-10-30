"""C-575 (reviewer C-524 F-C524-2): the CLI's estate clients never read the proxy environment and never follow a redirect.

``lifecycle_manager.cli._service_client`` builds the httpx client that carries the perimeter secret (and, on guarded
routes, the operator pair) to the registry, ledger, delegation, kill-switch and governor. A client built with httpx's
defaults reads ``HTTP_PROXY`` / ``ALL_PROXY`` from the process, so an ambient proxy would receive those headers in
clear, and a followed redirect could resend them elsewhere. Pinned here with local listeners only (made-up secret,
no network): a proxy variable pointing at a listener gets zero connections, and a 302 is returned, not followed.

Scope, stated plainly (reviewer C-639): ``follow_redirects=False`` is httpx 0.28.1's own default, so that half of the
change is a pin against a future default or an explicit True, not a behaviour change today; ``trust_env=False`` also
stops httpx reading ``SSL_CERT_FILE`` / ``SSL_CERT_DIR`` and ``.netrc`` (httpx ``create_ssl_context`` reads the two
variables only when trust_env is true). The ``serve`` verb's own clients are NOT covered here.
"""
from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from field_core import authn
from lifecycle_manager import cli

SERVICES = sorted(cli._SERVICE_URLS)
SECRET = "c575-made-up-perimeter-secret"
PROXY_VARS = ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy", "HTTPS_PROXY", "https_proxy")


class _Listener:
    """A TCP listener that counts connections (the stand-in for an ambient proxy)."""

    def __init__(self) -> None:
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(8)
        self.sock.settimeout(0.2)
        self.hits = 0
        self._stop = False
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.sock.getsockname()[1]}"

    def _run(self) -> None:
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
            except (socket.timeout, OSError):
                continue
            self.hits += 1
            conn.close()

    def close(self) -> None:
        self._stop = True
        self._t.join(1)
        self.sock.close()


def _closed_port_url() -> str:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return f"http://127.0.0.1:{port}"


@pytest.fixture
def secret(monkeypatch):
    monkeypatch.setenv(authn.ENV_VAR, SECRET)


@pytest.mark.parametrize("service", SERVICES)
def test_an_ambient_proxy_gets_no_connection_from_the_cli_client(monkeypatch, secret, service):
    proxy = _Listener()
    try:
        for var in PROXY_VARS:
            monkeypatch.setenv(var, proxy.url)
        monkeypatch.delenv("NO_PROXY", raising=False)
        monkeypatch.delenv("no_proxy", raising=False)
        monkeypatch.setenv(cli._SERVICE_URLS[service][0], _closed_port_url())
        _, client = cli._service_client(service, None, timeout=2.0)
        assert client.trust_env is False
        with pytest.raises(httpx.ConnectError):
            client.get("/health")              # straight to the (closed) service port, not through the proxy
        assert proxy.hits == 0
    finally:
        proxy.close()


class _Redirector(BaseHTTPRequestHandler):
    target = ""

    def do_GET(self):  # noqa: N802
        self.send_response(302)
        self.send_header("location", self.target)
        self.send_header("content-length", "0")
        self.end_headers()

    def log_message(self, *a):  # noqa: D401
        pass


def _serve(handler):
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


@pytest.mark.parametrize("service", SERVICES)
def test_the_cli_client_does_not_follow_a_redirect(monkeypatch, secret, service):
    seen: list[dict] = []

    class Other(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            seen.append(dict(self.headers))
            self.send_response(200)
            self.send_header("content-length", "0")
            self.end_headers()

        def log_message(self, *a):
            pass

    other = _serve(Other)
    redirector = type("R", (_Redirector,), {"target": f"http://127.0.0.1:{other.server_address[1]}/elsewhere"})
    first = _serve(redirector)
    try:
        monkeypatch.setenv(cli._SERVICE_URLS[service][0], f"http://127.0.0.1:{first.server_address[1]}")
        _, client = cli._service_client(service, None, timeout=2.0)
        assert client.follow_redirects is False
        assert client.get("/tokens").status_code == 302
        assert seen == [], "the redirect target was contacted, with the perimeter secret on the request"
    finally:
        first.shutdown()
        other.shutdown()


# ---- every client the verbs build goes through _service_client (reviewer C-639 F-C639-1) ---------------------------

PAIR = ("c575-op", "c575-made-up-key")          # made up; never printed
HTTP_KEYS = ["registry_http", "delegation", "governor", "killswitch"]
BUILDERS = [
    pytest.param(lambda pair: cli.estate_clients(pair), id="estate_clients"),
    pytest.param(lambda pair: cli._provision_clients(pair), id="provision_clients"),
]


def _plain_guarded(client: httpx.Client, pair) -> None:
    assert type(client) is httpx.Client, type(client)       # the CLI's own builder, not an api.py client class
    assert client.trust_env is False and client.follow_redirects is False
    assert isinstance(client.auth, cli.GuardedOperatorAuth)
    assert client.headers.get(authn.HEADER) == SECRET        # the perimeter secret rides every request


@pytest.mark.parametrize("pair", [None, PAIR], ids=["no_pair", "pair"])
@pytest.mark.parametrize("build", BUILDERS)
def test_every_http_client_the_verbs_build_comes_from_the_cli_builder(secret, build, pair):
    clients = build(pair)
    for key in HTTP_KEYS:
        _plain_guarded(clients[key], pair)


@pytest.mark.parametrize("pair", [None, PAIR], ids=["no_pair", "pair"])
@pytest.mark.parametrize("build", BUILDERS)
def test_the_field_core_wrappers_keep_the_injected_client(secret, build, pair):
    clients = build(pair)
    for key in ("registry", "ledger"):
        wrapper = clients[key]
        assert wrapper._own_client is False, key              # an own-client wrapper would read the proxy environment
        _plain_guarded(wrapper._client, pair)
    assert clients["registry"]._client is clients["registry_http"]


@pytest.mark.parametrize("build", BUILDERS)
def test_the_builders_return_exactly_the_clients_the_engine_expects(secret, build):
    assert sorted(build(None)) == sorted(["registry", "registry_http", "delegation", "governor", "killswitch", "ledger"])
