#!/usr/bin/env python3
"""One local listener that path-routes to the demo's services: the demo's counterpart of the estate's Caddy proxy.

    python path_proxy.py --port 18081 --route registry=51001 --route ledger=51002 ...

``GET /<name>/<rest>`` is forwarded to ``127.0.0.1:<port of name>`` as ``GET /<rest>`` (the prefix is stripped, as Caddy's
``handle_path`` does, so each service still sees root paths and ``/health`` stays an open path). A path with no known
prefix is a 404. The two internal key-rotation routes (``/operator/verify-hash``, ``/operator/rotation-state``) are
refused with 403 unless the request is from loopback with no ``X-Forwarded-For``, as ``integration/demo/Caddyfile`` does.
Headers (``x-field-auth``, the operator pair) and bodies are forwarded unchanged; a redirect is passed through, never
followed. ``--port 0`` takes a free port. The chosen port is the first line printed: ``listening <port>``. Standard
library only; bound to 127.0.0.1 only. A demo and test helper, not a production proxy: bodies are buffered and there is no TLS.
"""

from __future__ import annotations

import argparse
import http.client
import http.server
import ipaddress
import sys
import threading

HOP_BY_HOP = frozenset({"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
                        "transfer-encoding", "upgrade", "host", "content-length"})
INTERNAL_ROUTES = ("/operator/verify-hash", "/operator/rotation-state")
BACKEND_TIMEOUT_S = 60.0


def split_route(path: str, routes: dict[str, int]) -> tuple[int, str] | None:
    """``(backend port, path to send)`` for ``/<name>/<rest>`` (or ``/<name>``), or None when no prefix matches."""
    target = path.split("#", 1)[0]
    for name, port in routes.items():
        prefix = f"/{name}"
        if target == prefix:
            return port, "/"
        if target.startswith(prefix + "/") or target.startswith(prefix + "?"):
            rest = target[len(prefix):]
            return port, rest if rest.startswith("/") else "/" + rest
    return None


def internal_route_refused(path: str, client_ip: str, headers) -> bool:
    bare = path.split("?", 1)[0]
    if not any(route in bare for route in INTERNAL_ROUTES):
        return False
    try:
        loopback = ipaddress.ip_address(client_ip).is_loopback
    except ValueError:
        loopback = False
    return (not loopback) or headers.get("X-Forwarded-For") is not None


def make_handler(routes: dict[str, int]):
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:   # the demo's own output is the product
            pass

        def _reply(self, status: int, body: bytes, content_type: str = "text/plain; charset=utf-8", extra=()) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            for key, value in extra:
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _proxy(self) -> None:
            if internal_route_refused(self.path, self.client_address[0], self.headers):
                return self._reply(403, b"internal route: loopback only")
            hit = split_route(self.path, routes)
            if hit is None:
                return self._reply(404, b'{"detail":"no such service prefix"}', "application/json")
            port, path = hit
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP}
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=BACKEND_TIMEOUT_S)
            try:
                conn.request(self.command, path, body=body, headers=headers)
                resp = conn.getresponse()
                data = resp.read()
                extra = [(k, v) for k, v in resp.getheaders() if k.lower() not in HOP_BY_HOP]
            except (OSError, http.client.HTTPException):
                return self._reply(502, b'{"detail":"backend unreachable"}', "application/json")
            finally:
                conn.close()
            self.send_response(resp.status)
            for key, value in extra:
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _proxy

    return Handler


def serve(port: int, routes: dict[str, int]) -> http.server.ThreadingHTTPServer:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), make_handler(routes))
    server.daemon_threads = True
    return server


def parse_routes(items: list[str]) -> dict[str, int]:
    routes: dict[str, int] = {}
    for item in items:
        name, _, port = item.partition("=")
        if not name or not port.isdigit() or not 0 < int(port) < 65536 or "/" in name:
            raise SystemExit(f"error: --route must be NAME=PORT (got an invalid value for {name or '?'})")
        routes[name] = int(port)
    return routes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="path_proxy", description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=0, help="listen port on 127.0.0.1 (0 = a free port)")
    ap.add_argument("--route", action="append", default=[], metavar="NAME=PORT")
    args = ap.parse_args(argv)
    routes = parse_routes(args.route)
    if not routes:
        print("error: at least one --route NAME=PORT is required", file=sys.stderr)
        return 2
    try:
        server = serve(args.port, routes)
    except OSError as exc:
        print(f"error: cannot listen on 127.0.0.1:{args.port} ({type(exc).__name__})", file=sys.stderr)
        return 2
    print(f"listening {server.server_address[1]}", flush=True)
    try:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
