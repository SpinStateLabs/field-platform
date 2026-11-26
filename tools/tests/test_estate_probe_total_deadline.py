"""B-1074-TOTAL-DEADLINE: estate_probe --timeout bounds the WHOLE request, not each socket operation.

A slowloris server that sends one byte every TRICKLE seconds never trips a per-operation timeout, so before this fix a
request could outlast --timeout many times over and still come back 200 (measured: 34 s, and 78.6 s with trickled
headers, at --timeout 2). Every case here must end near --timeout and as a transport error (fail closed), never as an
answer. Local loopback servers only; nothing leaves the host."""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

import pytest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import estate_probe as ep  # noqa: E402
import phase_g_check as pg  # noqa: E402

TIMEOUT = 1.0    # --timeout under test
TRICKLE = 0.2    # one byte every TRICKLE s: far below TIMEOUT, so no single socket read ever times out
SLACK = 1.5      # a request must end within TIMEOUT + SLACK


class Slowloris:
    """A loopback HTTP server that answers 200 with a valid JSON body, one byte at a time. ``mode`` = "body" sends the
    headers at once and trickles the body; "headers" trickles the status line and headers too; "close" trickles a
    body with no Content-Length (the end of the body is the close)."""

    def __init__(self, mode: str, body: bytes = b'{"service": "sealed-ledger", "ok": true}'):
        self.mode, self.body, self.stop = mode, body, threading.Event()
        self.srv = socket.socket()
        self.srv.bind(("127.0.0.1", 0))
        self.srv.listen(8)
        self.srv.settimeout(0.2)
        self.base = f"http://127.0.0.1:{self.srv.getsockname()[1]}"
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while not self.stop.is_set():
            try:
                conn, _ = self.srv.accept()
            except OSError:
                continue
            threading.Thread(target=self._answer, args=(conn,), daemon=True).start()

    def _answer(self, conn):
        try:
            conn.settimeout(5)
            conn.recv(65536)                                   # the request (small, one read is enough here)
            head = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            if self.mode != "close":
                head += b"Content-Length: " + str(len(self.body)).encode() + b"\r\n"
            head += b"Connection: close\r\n\r\n"
            slow = (head + self.body) if self.mode == "headers" else self.body
            if self.mode != "headers":
                conn.sendall(head)
            for i in range(len(slow)):
                if self.stop.is_set():
                    break
                conn.sendall(slow[i:i + 1])
                time.sleep(TRICKLE)
        except OSError:
            pass
        finally:
            conn.close()

    def close(self):
        self.stop.set()
        self.srv.close()


@pytest.fixture(params=["body", "headers", "close"])
def slow(request):
    server = Slowloris(request.param)
    yield server
    server.close()


def test_a_trickled_answer_fails_closed_within_the_timeout(slow):
    estate = ep.Estate(slow.base, None, timeout=TIMEOUT)
    start = time.monotonic()
    status, body = estate.call("GET", "/ledger/health", auth=False)
    took = time.monotonic() - start
    assert took < TIMEOUT + SLACK, f"request took {took:.1f}s against --timeout {TIMEOUT}"
    assert status == 0 and body == {"transport_error": "TimeoutError"}


def test_the_cli_exits_non_zero_on_a_trickled_estate_and_stays_near_the_timeout(slow):
    ep.RESULTS.clear()
    start = time.monotonic()
    code = ep.main(["--base", slow.base, "--timeout", str(TIMEOUT), "health", "--only", "ledger"])
    took = time.monotonic() - start
    ep.RESULTS.clear()
    assert code != 0
    assert took < 3 * (TIMEOUT + SLACK)            # health makes a few calls; each one is bounded, none is 30 s+


def test_a_fast_answer_is_unchanged():
    body = b'{"service": "sealed-ledger"}'

    class Fast(Slowloris):
        def _answer(self, conn):
            try:
                conn.recv(65536)
                conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: "
                             + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
            finally:
                conn.close()

    server = Fast("body")
    try:
        assert ep.Estate(server.base, None, timeout=TIMEOUT).call("GET", "/ledger/health", auth=False) == \
            (200, {"service": "sealed-ledger"})
    finally:
        server.close()


class Busy(Slowloris):
    """Answers 503 with ``Retry-After: 1`` to the first ``busy`` requests, then 200."""

    def __init__(self, busy: int):
        self.busy, self.seen, self._count = busy, 0, threading.Lock()
        super().__init__("body")

    def _answer(self, conn):
        try:
            conn.settimeout(5)
            conn.recv(65536)
            with self._count:
                self.seen += 1
                refuse = self.seen <= self.busy
            status = b"503 Service Unavailable\r\nRetry-After: 1" if refuse else b"200 OK"
            body = b'{"service": "sealed-ledger"}'
            conn.sendall(b"HTTP/1.1 " + status + b"\r\nContent-Type: application/json\r\nContent-Length: "
                         + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n" + body)
        except OSError:
            pass
        finally:
            conn.close()


@pytest.mark.parametrize("busy, expected, requests", [(2, 200, 3), (99, 503, 1 + pg.RETRY_MAX)], ids=["recovers", "spent"])
def test_a_retry_layers_waits_are_outside_the_timeout(busy, expected, requests):
    """The waits add up to more than --timeout: the answer is still the server's own, never a transport error."""
    server = Busy(busy)
    try:
        estate = pg._with_503_retry(ep.Estate(server.base, None, timeout=TIMEOUT))
        start = time.monotonic()
        status, _ = estate.call("GET", "/ledger/health", auth=False)
        assert time.monotonic() - start > TIMEOUT, "the case must outlast one attempt's limit"
        assert status == expected and server.seen == requests
    finally:
        server.close()


def test_a_trickled_answer_after_a_wait_still_fails_closed():
    class BusyThenSlow(Busy):
        def _answer(self, conn):
            with self._count:
                first = self.seen == 0
            if first:
                return Busy._answer(self, conn)
            with self._count:
                self.seen += 1
            return Slowloris._answer(self, conn)

    server = BusyThenSlow(1)
    try:
        estate = pg._with_503_retry(ep.Estate(server.base, None, timeout=TIMEOUT))
        start = time.monotonic()
        status, body = estate.call("GET", "/ledger/health", auth=False)
        assert status == 0 and body == {"transport_error": "TimeoutError"}
        assert time.monotonic() - start < 1 + TIMEOUT + SLACK        # one wait, then one bounded attempt
    finally:
        server.close()
