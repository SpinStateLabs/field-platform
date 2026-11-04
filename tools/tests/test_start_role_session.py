"""tools/start_role_session.py sends the workspace API key, so its HTTP call must not read the proxy environment and must
not follow a redirect (the C-57 lint's rule, found red on main after #532).

Before: `urllib.request.urlopen(req)` used the default opener: it honours `HTTP(S)_PROXY` (the key can go to a proxy) and
follows a 3xx, forwarding the custom `x-api-key` header to the redirect target. Now a module opener built from a
no-redirect handler and `ProxyHandler({})`, the same shape as renew_token.py and estate_probe.py. The tests use two local
servers; nothing leaves the machine."""

from __future__ import annotations

import importlib.util
import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "start_role_session.py"


def _load():
    spec = importlib.util.spec_from_file_location("start_role_session_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Server:
    """A local HTTP server that records every request and answers with `reply(handler) -> (status, headers, body)`."""

    def __init__(self, reply):
        self.requests: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("content-length") or 0)
                outer.requests.append({"path": self.path, "headers": dict(self.headers), "body": self.rfile.read(n)})
                status, headers, body = reply(self)
                self.send_response(status)
                for k, v in headers.items():
                    self.send_header(k, v)
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


@pytest.fixture()
def servers():
    made: list[Server] = []

    def make(reply):
        s = Server(reply)
        made.append(s)
        return s

    yield make
    for s in made:
        s.close()


@pytest.fixture()
def mod(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-key-0000")
    for v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(urllib.request, "_opener", None)   # urlopen caches its global opener from the first call in the process
    return _load()


def test_a_success_sends_the_key_and_headers_and_returns_the_json(mod, servers, monkeypatch):
    ok = servers(lambda h: (200, {"content-type": "application/json"}, b'{"id": "sess_1"}'))
    monkeypatch.setattr(mod, "API_BASE", ok.url)
    assert mod.call("/v1/sessions", {"a": 1}) == {"id": "sess_1"}
    req = ok.requests[0]
    assert req["path"] == "/v1/sessions" and json.loads(req["body"]) == {"a": 1}
    h = {k.lower(): v for k, v in req["headers"].items()}
    assert h["x-api-key"] == "synthetic-key-0000" and h["anthropic-version"] == "2023-06-01" and h["content-type"] == "application/json"


def test_a_redirect_is_not_followed_and_the_key_never_reaches_the_target(mod, servers, monkeypatch):
    target = servers(lambda h: (200, {}, b"{}"))
    bouncer = servers(lambda h: (302, {"location": target.url + "/stolen"}, b""))
    monkeypatch.setattr(mod, "API_BASE", bouncer.url)
    with pytest.raises(SystemExit) as e:
        mod.call("/v1/sessions", {})
    assert "302" in str(e.value)                       # a 3xx is an answer, reported as one
    assert len(bouncer.requests) == 1 and target.requests == []


def test_the_proxy_environment_is_ignored(mod, servers, monkeypatch):
    proxy = servers(lambda h: (200, {}, b'{"via": "proxy"}'))
    origin = servers(lambda h: (200, {}, b'{"via": "origin"}'))
    monkeypatch.setenv("HTTP_PROXY", proxy.url)
    monkeypatch.setenv("http_proxy", proxy.url)
    monkeypatch.setenv("ALL_PROXY", proxy.url)
    for v in ("NO_PROXY", "no_proxy"):          # a no_proxy that lists loopback would hide the proxy from the default opener
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(urllib.request, "_opener", None)
    fresh = _load()                       # the opener is built at import: load AFTER the proxy variables are set
    monkeypatch.setattr(fresh, "API_BASE", origin.url)
    assert fresh.call("/v1/sessions", {}) == {"via": "origin"}
    assert proxy.requests == [] and len(origin.requests) == 1


def test_without_a_key_nothing_is_sent(mod, servers, monkeypatch):
    srv = servers(lambda h: (200, {}, b"{}"))
    monkeypatch.setattr(mod, "API_BASE", srv.url)
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(SystemExit) as e:
        mod.call("/v1/sessions", {})
    assert "not set" in str(e.value) and srv.requests == []


def test_an_http_error_exits_with_the_status_and_a_cut_body(mod, servers, monkeypatch):
    bad = servers(lambda h: (400, {}, b"x" * 1000))
    monkeypatch.setattr(mod, "API_BASE", bad.url)
    with pytest.raises(SystemExit) as e:
        mod.call("/v1/sessions", {})
    assert str(e.value).startswith("HTTP 400: ") and len(str(e.value)) <= len("HTTP 400: ") + 400
