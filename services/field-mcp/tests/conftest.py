"""A stub platform service on loopback: made-up replies, recorded requests, no real network, no real key."""
from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from field_mcp.config import Config, ServiceConfig

KEY = "stub-key-" + "Q7x9" * 4
MARK = "stub-echo-" + "Z3k1" * 3


class Stub:
    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.routes: dict[tuple[str, str], tuple[int, object, dict]] = {}
        self.delay = 0.0
        stub = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _do(self):
                n = int(self.headers.get("content-length") or 0)
                raw = self.rfile.read(n) if n else b""
                path = self.path.split("?")[0]
                stub.requests.append({"method": self.command, "target": self.path, "path": path,
                                      "headers": {k.lower(): v for k, v in self.headers.items()}, "body": raw})
                if stub.delay:
                    time.sleep(stub.delay)
                status, body, extra = stub.routes.get((self.command, path), (200, {"ok": True}, {}))
                data = body if isinstance(body, bytes) else (body.encode() if isinstance(body, str) else json.dumps(body).encode())
                ctype = extra.get("content-type", "application/json")
                self.send_response(status)
                self.send_header("content-type", ctype)
                self.send_header("content-length", str(len(data)))
                for k, v in extra.items():
                    if k != "content-type":
                        self.send_header(k, v)
                self.end_headers()
                try:
                    self.wfile.write(data)
                except OSError:
                    pass

            do_GET = do_POST = do_PUT = do_PATCH = _do

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def stub():
    s = Stub()
    yield s
    s.close()


def config_for(stub: Stub, *services: str, key: str = KEY, tier: int = 1) -> Config:
    from field_mcp.catalog import SERVICES
    return Config(tier=tier, services={s: ServiceConfig(stub.base, key) for s in (services or SERVICES)})
