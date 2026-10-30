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

The second half of the file is behavioural (reviewer C-732): for each builder and each of ``sweep`` / ``provision`` /
``decommission`` (the engine replaced by a stand-in that records what it is handed), with and without an operator pair,
every client is exercised against five local services, a counting listener as the ambient proxy and, in a second pass,
302s to a target: zero proxy connections, zero redirect hits, each request on ITS service, the perimeter secret on
every request and the operator pair on guarded routes only.
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
    assert client.auth._pair == pair                         # the operator pair reaches the guarded auth, or None does
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
    # each wrapper's client belongs to ITS service: its base URL and its guarded-route set (N10: the ledger wrapper on the
    # registry's client would send the registry's guarded routes the operator pair)
    for key in ("registry", "ledger"):
        wrapper = clients[key]
        assert str(wrapper._client.base_url).rstrip("/") == wrapper._base, key
        assert wrapper._client.auth._routes == cli.GUARDED_ROUTES.get(key, ()), key
    assert clients["ledger"]._client is not clients["registry"]._client


@pytest.mark.parametrize("build", BUILDERS)
def test_the_builders_return_exactly_the_clients_the_engine_expects(secret, build):
    assert sorted(build(None)) == sorted(["registry", "registry_http", "delegation", "governor", "killswitch", "ledger"])


# ---- behaviour, per builder and per verb (reviewer C-732 F-C732-2, -3) -----------------------------------------------

import contextlib
import json

from typer.testing import CliRunner

# the plain client each estate_clients key holds -> the service it must talk to, and one request on a guarded route
_PLAIN = {
    "registry_http": ("registry", lambda c: c.post("/agents", json={})),
    "delegation": ("delegation", lambda c: c.post("/tokens", json={})),
    "governor": ("governor", lambda c: c.put("/caps/a", json={})),
    "killswitch": ("killswitch", lambda c: c.post("/kill/a", json={})),
}
# the paths each service may legitimately see from these calls: anything else means a client on the wrong service
_EXPECTED = {
    "registry": {("POST", "/agents"), ("GET", "/agents/a")},
    "delegation": {("POST", "/tokens")},
    "governor": {("PUT", "/caps/a")},
    "killswitch": {("POST", "/kill/a")},
    "ledger": {("GET", "/events")},
}
_GUARDED = {("POST", "/agents"), ("POST", "/tokens"), ("PUT", "/caps/a"), ("POST", "/kill/a")}


class _Service:
    """A local HTTP server standing in for one estate service: records every request, optionally answers 302."""

    def __init__(self, redirect_to: str | None = None) -> None:
        outer = self
        self.hits: list[tuple[str, str, dict]] = []

        class H(BaseHTTPRequestHandler):
            def _do(self):
                outer.hits.append((self.command, self.path, {k.lower(): v for k, v in self.headers.items()}))
                n = int(self.headers.get("content-length") or 0)
                if n:
                    self.rfile.read(n)
                if redirect_to:
                    self.send_response(302)
                    self.send_header("location", redirect_to)
                    self.send_header("content-length", "0")
                else:
                    body = b"{}"
                    self.send_response(200)
                    self.send_header("content-type", "application/json")
                    self.send_header("content-length", str(len(body)))
                self.end_headers()
                if not redirect_to:
                    self.wfile.write(body)

            do_GET = do_POST = do_PUT = do_PATCH = _do  # noqa: N815

            def log_message(self, *a):
                pass

        self.srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.srv.server_address[1]}"

    def close(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()


@contextlib.contextmanager
def _estate(monkeypatch, *, redirect: bool):
    """Five local services, a counting listener as the ambient proxy, and (redirect) one target for every 302."""
    proxy, target = _Listener(), _Service()
    services = {name: _Service(target.url if redirect else None) for name in _EXPECTED}
    try:
        for var in PROXY_VARS:
            monkeypatch.setenv(var, proxy.url)
        for var in ("NO_PROXY", "no_proxy"):
            monkeypatch.delenv(var, raising=False)
        for name, svc in services.items():
            monkeypatch.setenv(cli._SERVICE_URLS[name][0], svc.url)
        yield services, proxy, target
    finally:
        for svc in (*services.values(), target):
            svc.close()
        proxy.close()


def _exercise(clients: dict) -> set[str]:
    """One guarded request per plain client and one read per field-core wrapper; returns the services touched."""
    wanted: set[str] = set()
    for key, (service, call) in _PLAIN.items():
        if key in clients:
            wanted.add(service)
            with contextlib.suppress(Exception):
                call(clients[key])
    if "registry" in clients:
        wanted.add("registry")
        with contextlib.suppress(Exception):
            clients["registry"].get_agent("a")
    if "ledger" in clients:
        wanted.add("ledger")
        with contextlib.suppress(Exception):
            clients["ledger"].events()
    return wanted


def _judge(make_clients, pair, *, redirect: bool, monkeypatch) -> None:
    """``make_clients`` runs inside the estate: the service URLs are read when a client is built."""
    with _estate(monkeypatch, redirect=redirect) as (services, proxy, target):
        wanted = _exercise(make_clients())
        assert proxy.hits == 0, "a client connected to the ambient proxy"
        assert target.hits == [], "a client followed a redirect"
        for name, svc in services.items():
            seen = {(m, p) for m, p, _ in svc.hits}
            if name not in wanted:
                assert not svc.hits, (name, svc.hits)
                continue
            assert svc.hits, f"{name}: its client never reached it"        # the request went to ITS service
            assert seen <= _EXPECTED[name], (name, seen)                    # and to nothing it should not see
            for m, p, headers in svc.hits:
                assert headers.get(authn.HEADER) == SECRET, (name, m, p)    # the perimeter secret rides every request
                carries = "x-field-operator" in headers
                assert carries is (bool(pair) and (m, p) in _GUARDED), (name, m, p, carries)
                if carries:
                    assert (headers["x-field-operator"], headers["x-field-operator-key"]) == pair


@pytest.mark.parametrize("redirect", [False, True], ids=["direct", "redirect"])
@pytest.mark.parametrize("pair", [None, PAIR], ids=["no_pair", "pair"])
@pytest.mark.parametrize("build", BUILDERS)
def test_every_builder_entry_talks_to_its_own_service_without_proxy_or_redirect(monkeypatch, secret, build, pair,
                                                                                redirect):
    _judge(lambda: build(pair), pair, redirect=redirect, monkeypatch=monkeypatch)


def test_every_builder_entry_honours_the_timeout(secret):
    clients = cli.estate_clients(None, timeout=3.0)
    for key in _PLAIN:
        assert clients[key].timeout == httpx.Timeout(3.0), key


# the verbs: the engine is replaced by a stand-in that records what it was handed, then stops the verb


class _Stop(Exception):
    pass


class _CaptureEngine:
    kwargs: dict | None = None

    def __init__(self, **kw):
        type(self).kwargs = kw

    def __getattr__(self, name):                      # the verb's first call on the engine ends the run
        raise _Stop(name)


def _handed_to_the_engine(monkeypatch, tmp_path, verb: str, pair) -> dict:
    from field_core import operator_auth
    from lifecycle_manager import engine as engine_mod

    _CaptureEngine.kwargs = None
    monkeypatch.setattr(engine_mod, "LifecycleEngine", _CaptureEngine)
    monkeypatch.setattr(cli, "operator_pair", lambda *a, **k: pair)
    fake = type("Auth", (), {"mode": "enforce", "authenticated": True, "failure": None, "operator": None})()
    monkeypatch.setattr(operator_auth, "authenticate", lambda *a, **k: fake)
    monkeypatch.setattr(operator_auth, "bind", lambda *a, **k: None)
    monkeypatch.setattr(operator_auth, "bind_body_operator", lambda by, *a, **k: by)
    roster, manifest = tmp_path / "roster.csv", tmp_path / "agent.yaml"
    roster.write_text("agent_id,owner\n", encoding="utf-8")
    manifest.write_text("name: c575\n", encoding="utf-8")
    argv = {
        "sweep": ["sweep", "--roster", str(roster), "--auto-kill-orphans"],
        "provision": ["provision", "--manifest", str(manifest), "--owner", "o", "--domain", "d", "--grantor", "g",
                      "--ttl-days", "1"],
        "decommission": ["decommission", "a", "--by", "b", "--reason", "r"],
    }[verb]
    CliRunner().invoke(cli.app, argv)
    assert _CaptureEngine.kwargs is not None, f"{verb} never built an engine"
    return _CaptureEngine.kwargs


VERBS = {
    "sweep": {"registry", "delegation", "ledger", "killswitch"},
    "provision": {"registry", "registry_http", "delegation", "governor", "killswitch", "ledger"},
    "decommission": {"registry", "registry_http", "delegation", "governor", "killswitch", "ledger"},
}


@pytest.mark.parametrize("redirect", [False, True], ids=["direct", "redirect"])
@pytest.mark.parametrize("pair", [None, PAIR], ids=["no_pair", "pair"])
@pytest.mark.parametrize("verb", sorted(VERBS))
def test_every_verb_hands_the_engine_clients_that_ignore_proxy_and_redirect(monkeypatch, tmp_path, secret, verb,
                                                                           pair, redirect):
    def make():
        kwargs = _handed_to_the_engine(monkeypatch, tmp_path, verb, pair)
        clients = {k: v for k, v in kwargs.items() if k in VERBS[verb]}
        assert set(clients) == VERBS[verb], (verb, sorted(kwargs))
        return clients

    _judge(make, pair, redirect=redirect, monkeypatch=monkeypatch)
