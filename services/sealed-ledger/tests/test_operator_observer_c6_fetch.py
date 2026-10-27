"""C-6 observer, the real HTTP fetch (review of PR #42, L3): a ``/health`` answer is
read with a size cap and an overall deadline, so a target that trickles a body or
sends a huge one cannot hold a tick for long; either is treated like no answer
(nothing written, last state kept, retried next tick). Real sockets, a local stub."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sealed_ledger import operator_observer as ob

HEALTH = {"ok": True, "operator_mode": "off", "operator_registry_sha256_prefix": None,
          "operator_registry_rows": None}


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, status, raw, length=None):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw) if length is None else length))
        self.end_headers()

    def do_GET(self):  # noqa: N802
        try:
            if self.path == "/ok/health":
                raw = json.dumps(HEALTH).encode()
                self._send(200, raw)
                self.wfile.write(raw)
            elif self.path == "/big/health":
                raw = json.dumps({**HEALTH, "pad": "x" * (ob.MAX_HEALTH_BYTES + 10)}).encode()
                self._send(200, raw)
                self.wfile.write(raw)
            elif self.path == "/drip/health":
                raw = json.dumps(HEALTH).encode()
                self._send(200, raw)
                for i in range(len(raw)):                  # one byte every 0.25 s: ~20 s in all
                    self.wfile.write(raw[i:i + 1])
                    self.wfile.flush()
                    time.sleep(0.25)
            elif self.path == "/err/health":
                raw = json.dumps(HEALTH).encode()
                self._send(500, raw)
                self.wfile.write(raw)
            elif self.path == "/notjson/health":
                self._send(200, b"<html>")
                self.wfile.write(b"<html>")
        except OSError:
            pass                                           # the client hung up: expected for /drip


@pytest.fixture(scope="module")
def stub():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_a_normal_answer_is_decoded(stub):
    assert ob.http_fetch(f"{stub}/ok/health") == HEALTH


@pytest.mark.parametrize("path", ["/big/health", "/err/health", "/notjson/health"])
def test_an_oversize_non_200_or_non_json_answer_is_no_answer(stub, path):
    assert ob.http_fetch(f"{stub}{path}") is None


def test_a_trickled_body_is_cut_off_at_the_deadline(stub):
    t0 = time.monotonic()
    assert ob.http_fetch(f"{stub}/drip/health") is None
    took = time.monotonic() - t0
    # the deadline (FETCH_TIMEOUT_S) plus at most one last read; the whole body would take ~20 s
    assert took < 2 * ob.FETCH_TIMEOUT_S + 1.0, took
