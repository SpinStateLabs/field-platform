"""DEMO-ONEPORT: ``integration/demo/path_proxy.py`` and the ``run_demo.sh`` that uses it.

The demo used to start seven services on fixed ports 8001-8007 and post to :8001 and :8002, so any other listener on one
of them broke it. It now starts the services on free loopback ports behind ONE path-routed listener (the estate's Caddy
map: ``/<service>/...``), the port set by ``PORT`` or a free default. These tests pin the proxy's routing and refusals with
real sockets and stub backends, and pin that ``run_demo.sh`` keeps no fixed service port. (The full run needs the installed
service commands; it was run by hand with 8001 and 8002 occupied and exits 0.)"""
from __future__ import annotations

import http.client
import http.server
import importlib.util
import json
import re
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("demo_path_proxy", ROOT / "integration" / "demo" / "path_proxy.py")
pp = importlib.util.module_from_spec(_spec)
sys.modules["demo_path_proxy"] = pp
_spec.loader.exec_module(pp)
RUN_DEMO = (ROOT / "integration" / "demo" / "run_demo.sh").read_text(encoding="utf-8")
SERVICES = ("registry", "ledger", "delegation", "sentinel", "killswitch", "governor", "replay")


def backend(name: str, seen: list):
    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _do(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(n) if n else b""
            seen.append({"svc": name, "method": self.command, "path": self.path, "body": body,
                         "auth": self.headers.get("x-field-auth"), "host": self.headers.get("Host")})
            if self.path.startswith("/redirect"):
                self.send_response(302)
                self.send_header("Location", "/health")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if self.path.startswith("/created"):
                code, payload = 201, b'{"made": true}'
            elif self.path.startswith("/missing"):
                code, payload = 404, b'{"detail": "nope"}'
            else:
                code, payload = 200, json.dumps({"svc": name, "path": self.path}).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(payload)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = _do

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    return srv


@pytest.fixture()
def stack():
    seen: list = []
    backs = {n: backend(n, seen) for n in ("registry", "ledger")}
    routes = {n: s.server_address[1] for n, s in backs.items()}
    proxy = pp.serve(0, routes)
    threading.Thread(target=proxy.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    yield proxy.server_address[1], routes, seen
    proxy.shutdown()
    proxy.server_close()
    for s in backs.values():
        s.shutdown()
        s.server_close()


def call(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        c.request(method, path, body=body, headers=headers or {})
        r = c.getresponse()
        return r.status, r.read(), dict(r.getheaders())
    finally:
        c.close()


def test_a_service_prefix_is_stripped_and_routed_to_its_own_backend(stack):
    port, _, seen = stack
    status, body, _ = call(port, "GET", "/registry/health")
    assert status == 200 and json.loads(body) == {"svc": "registry", "path": "/health"}
    status, body, _ = call(port, "GET", "/ledger/verify")
    assert json.loads(body) == {"svc": "ledger", "path": "/verify"}
    assert [(s["svc"], s["path"]) for s in seen] == [("registry", "/health"), ("ledger", "/verify")]


def test_the_query_string_is_kept_and_a_bare_prefix_is_the_root(stack):
    port, _, seen = stack
    call(port, "GET", "/registry/agents?status=active&domain=finance")
    call(port, "GET", "/ledger")
    call(port, "GET", "/ledger?x=1")
    assert [s["path"] for s in seen] == ["/agents?status=active&domain=finance", "/", "/?x=1"]


def test_a_body_and_the_auth_headers_are_forwarded_unchanged(stack):
    port, _, seen = stack
    payload = json.dumps({"agent_id": "a1"}).encode()
    status, _, _ = call(port, "POST", "/registry/agents", payload,
                        {"Content-Type": "application/json", "x-field-auth": "made-up-secret"})
    assert status == 200
    assert seen[-1]["method"] == "POST" and seen[-1]["body"] == payload and seen[-1]["auth"] == "made-up-secret"
    assert seen[-1]["host"].startswith("127.0.0.1:")


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
def test_other_methods_pass_through(stack, method):
    port, _, seen = stack
    call(port, method, "/ledger/x", b"{}" if method != "DELETE" else None)
    assert seen[-1]["method"] == method


def test_the_status_of_the_backend_is_kept_and_a_redirect_is_not_followed(stack):
    port, _, seen = stack
    assert call(port, "POST", "/registry/created", b"{}")[0] == 201
    assert call(port, "GET", "/registry/missing")[0] == 404
    status, _, headers = call(port, "GET", "/registry/redirect")
    assert status == 302 and headers["Location"] == "/health"
    assert [s["path"] for s in seen if s["path"].startswith("/redirect")] == ["/redirect"]   # followed never


def test_the_proxy_listens_on_loopback_only():
    srv = pp.serve(0, {"registry": 1})
    try:
        assert srv.server_address[0] == "127.0.0.1"
    finally:
        srv.server_close()


def test_an_unknown_prefix_is_404_and_reaches_no_backend(stack):
    port, _, seen = stack
    for path in ("/nope/health", "/", "/registryx/health", "/health"):
        assert call(port, "GET", path)[0] == 404
    assert seen == []


def test_a_dead_backend_is_502_not_a_hang(stack):
    port, routes, _ = stack
    dead = pp.serve(0, {"registry": 1})            # nothing listens on port 1
    threading.Thread(target=dead.serve_forever, kwargs={"poll_interval": 0.02}, daemon=True).start()
    try:
        assert call(dead.server_address[1], "GET", "/registry/health")[0] == 502
    finally:
        dead.shutdown()
        dead.server_close()


def test_the_internal_rotation_routes_are_refused_behind_a_proxy_hop_and_open_from_loopback(stack):
    port, _, seen = stack
    for path in ("/registry/operator/verify-hash", "/ledger/operator/rotation-state"):
        assert call(port, "GET", path, headers={"X-Forwarded-For": "10.0.0.9"})[0] == 403
        assert call(port, "GET", path)[0] == 200
    assert len(seen) == 2          # only the two loopback calls reached a backend


def test_internal_route_refusal_logic():
    class H(dict):
        def get(self, k, d=None):
            return super().get(k, d)

    assert pp.internal_route_refused("/x/operator/verify-hash", "10.0.0.1", H())
    assert pp.internal_route_refused("/x/operator/rotation-state?a=1", "192.168.1.5", H())
    assert pp.internal_route_refused("/x/operator/verify-hash", "127.0.0.1", H({"X-Forwarded-For": "1.2.3.4"}))
    assert not pp.internal_route_refused("/x/operator/verify-hash", "127.0.0.1", H())
    assert not pp.internal_route_refused("/x/health", "10.0.0.1", H())
    assert pp.internal_route_refused("/x/operator/verify-hash", "not-an-ip", H())   # an unparseable peer is not loopback


def test_split_route_and_route_parsing():
    routes = {"registry": 1, "ledger": 2}
    assert pp.split_route("/registry/a/b?c=d", routes) == (1, "/a/b?c=d")
    assert pp.split_route("/ledger", routes) == (2, "/")
    assert pp.split_route("/registryx/a", routes) is None
    assert pp.parse_routes(["a=1", "b=65535"]) == {"a": 1, "b": 65535}
    for bad in ("a", "a=", "a=x", "a=0", "a=70000", "=5", "a/b=5"):
        with pytest.raises(SystemExit):
            pp.parse_routes([bad])


def test_port_zero_takes_a_free_port_and_a_taken_port_is_a_refusal():
    srv = pp.serve(0, {"registry": 1})
    port = srv.server_address[1]
    assert port != 0
    try:
        assert pp.main(["--port", str(port), "--route", "registry=1"]) == 2     # in use: named refusal, exit 2
    finally:
        srv.server_close()
    assert pp.main(["--port", "0"]) == 2                                          # no routes


# -- the demo script ---------------------------------------------------------------------------------------------------
def code_lines():
    return [ln for ln in RUN_DEMO.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def test_run_demo_keeps_no_fixed_service_port():
    hits = [ln for ln in code_lines() if re.search(r"(?<![\w.])800[1-9](?![\w])", ln)]
    assert hits == [], hits


def test_run_demo_starts_the_proxy_and_routes_every_service_by_path():
    text = "\n".join(code_lines())
    assert 'path_proxy.py" --port "$PORT"' in text and '${PORT:-}' in text
    for name in SERVICES:
        assert f'--route "{name}=$P_{name.upper()}"' in text, name
        assert f'serve --port "$P_{name.upper()}"' in text, name
        assert f'"$BASE/{name}"' in text, name


def test_run_demo_never_posts_to_a_literal_host_and_port():
    assert not re.search(r"127\.0\.0\.1:\d+", "\n".join(code_lines()).replace('"http://127.0.0.1:$PORT"', ""))


def test_run_demo_fails_loudly_when_a_service_is_not_healthy_behind_the_proxy():
    assert "NOT healthy through the proxy" in RUN_DEMO and "sys.exit(" in RUN_DEMO


def test_run_demo_exits_at_once_when_the_proxy_cannot_listen():
    text = "\n".join(code_lines())
    assert 'kill -0 "$PROXY_PID"' in text and "could not listen on 127.0.0.1:$PORT" in text and "exit 1" in text
