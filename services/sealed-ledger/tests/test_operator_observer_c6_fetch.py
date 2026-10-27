"""C-6 observer, the real HTTP fetch (review of PR #42, L3; independent review R2-L1): a
``/health`` answer is read with a size cap and ONE overall deadline for the whole exchange
(name lookup, connect, status line and headers, body), so a target that trickles its
headers or its body, or sends a huge answer, cannot hold a tick for long; each is treated
like no answer (nothing written, last state kept, retried next tick). Real sockets, a
local stub."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from sealed_ledger import operator_observer as ob

HEALTH = {"ok": True, "operator_mode": "off", "operator_registry_sha256_prefix": None,
          "operator_registry_rows": None}


#: set by /hdrdrip and /drip2 when the client has hung up (its socket closed)
HUNG_UP = {"hdrdrip": threading.Event(), "drip2": threading.Event()}


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
            elif self.path == "/hdrdrip/health":
                # R2-L1: the status line and HEADERS trickled one byte every 0.1 s (~30 s in all),
                # so no single read ever waits 3 s; the body would follow
                raw = json.dumps(HEALTH).encode()
                head = (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nX-Pad: "
                        + b"p" * 200 + b"\r\nContent-Length: " + str(len(raw)).encode() + b"\r\n\r\n")
                try:
                    for i in range(len(head)):
                        self.wfile.write(head[i:i + 1])
                        self.wfile.flush()
                        time.sleep(0.1)
                    self.wfile.write(raw)
                    self.wfile.flush()
                except OSError:
                    HUNG_UP["hdrdrip"].set()
                    raise
                self.close_connection = True
            elif self.path == "/drip2/health":
                raw = json.dumps(HEALTH).encode()
                self._send(200, raw)
                try:
                    for i in range(len(raw)):              # one byte every 0.1 s: ~8 s in all
                        self.wfile.write(raw[i:i + 1])
                        self.wfile.flush()
                        time.sleep(0.1)
                except OSError:
                    HUNG_UP["drip2"].set()
                    raise
            elif self.path == "/redir/health":
                # Y4: a 302 whose own body is a valid /health, pointing at a valid /health
                raw = json.dumps({**HEALTH, "operator_mode": "enforce"}).encode()
                self.send_response(302)
                self.send_header("Location", "/ok/health")
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            elif self.path.startswith("/size/"):
                # Y1: a valid JSON answer of exactly N bytes
                n = int(self.path.split("/")[2])
                head = json.dumps({**HEALTH, "pad": ""}).encode()
                raw = head[:-2] + b"x" * (n - len(head)) + b'"}'
                assert len(raw) == n
                self._send(200, raw)
                self.wfile.write(raw)
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


def test_trickled_headers_are_cut_off_at_one_overall_deadline(stub):
    """R2-L1 (independent review of PR #42, measured ~48 s): the deadline covers the status
    line and headers too, not only the body; each byte arrives well inside any per-read
    timeout, so only an overall deadline stops it."""
    HUNG_UP["hdrdrip"].clear()
    t0 = time.monotonic()
    assert ob.http_fetch(f"{stub}/hdrdrip/health") is None
    took = time.monotonic() - t0
    assert took < ob.FETCH_TIMEOUT_S + 0.5, took
    # and the connection was closed, not left open behind the timeout
    assert HUNG_UP["hdrdrip"].wait(5), "the client never closed the trickled connection"


def test_a_trickled_body_is_cut_off_at_the_same_single_deadline(stub):
    """One deadline for the whole exchange: no extra read after it (was up to 2 x FETCH_TIMEOUT_S)."""
    HUNG_UP["drip2"].clear()
    t0 = time.monotonic()
    assert ob.http_fetch(f"{stub}/drip2/health") is None
    took = time.monotonic() - t0
    assert took < ob.FETCH_TIMEOUT_S + 0.5, took
    assert HUNG_UP["drip2"].wait(5), "the client never closed the trickled connection"


@pytest.mark.parametrize("url", ["http://", "http://127.0.0.1:0/health", "ftp://127.0.0.1/health",
                                 "http://[::1/health", "not a url"])
def test_a_malformed_or_unreachable_url_is_no_answer_and_never_raises(url):
    t0 = time.monotonic()
    assert ob.http_fetch(url) is None
    assert time.monotonic() - t0 < ob.FETCH_TIMEOUT_S + 0.5


def test_a_hung_name_lookup_is_inside_the_same_deadline(monkeypatch):
    """The lookup is part of the connect: a resolver that hangs (10 s here) is abandoned at
    the deadline, not waited for."""
    import socket

    real = socket.getaddrinfo

    def slow(host, *args, **kwargs):
        if host == "slow-dns.invalid":
            time.sleep(10)
        return real(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", slow)
    t0 = time.monotonic()
    assert ob.http_fetch("http://slow-dns.invalid:8001/health") is None
    assert time.monotonic() - t0 < ob.FETCH_TIMEOUT_S + 0.5


def test_a_redirect_is_never_followed(stub):
    """R2-L3 Y4: a 302 is no answer, even when its own body and its target are valid answers."""
    assert ob.http_fetch(f"{stub}/ok/health") == HEALTH           # the target is a valid answer
    assert ob.http_fetch(f"{stub}/redir/health") is None


@pytest.mark.parametrize("size, accepted", [(65536, True), (65537, False)])
def test_the_body_cap_is_exactly_64_kib(stub, size, accepted):
    """R2-L3 Y1: 65536 bytes is accepted, 65537 refused (a tightened or loosened cap is caught)."""
    assert ob.MAX_HEALTH_BYTES == 65536
    got = ob.http_fetch(f"{stub}/size/{size}/health")
    if accepted:
        assert isinstance(got, dict) and got["operator_mode"] == "off" and len(got["pad"]) > 65000
    else:
        assert got is None
