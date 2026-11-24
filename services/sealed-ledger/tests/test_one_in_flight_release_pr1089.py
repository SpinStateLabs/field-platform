"""PR 1089 review conditions C1 and C2 (B-FIX-PR1089-release).

C1: the one-in-flight limit still holds AFTER an earlier whole-ledger request finished and after one raised. A double
release (an extra release in the awaiting coroutine) or a release that subtracts too much leaves the counter negative or
understated, so two whole-ledger reads would then run at once while every single-request test stays green.
C2: a GET /events with only ``agent_id`` is not a whole-ledger request: it is never refused by the admission check
(the attestation-reporter's canary row reads it).

Real uvicorn on loopback; the store's verify()/events() block on a counting semaphore, so each ``allow()`` lets exactly
ONE blocked call finish and nothing depends on parse speed.
"""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time

import pytest

from ledger_c2_support import three_segments
from sealed_ledger.api import create_app

ENV = "FIELD_LEDGER_HEAVY_INFLIGHT"


def _serve(app):
    import uvicorn

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="critical", timeout_graceful_shutdown=1.0))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.02)
    assert server.started
    return server, thread, port


def _get(port, path, timeout=10.0):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


class Stack:
    def __init__(self, tmp_path, monkeypatch, width=None):
        if width is not None:
            monkeypatch.setenv(ENV, str(width))
        self.store, _, _ = three_segments(tmp_path / "ledger")
        self.entered = threading.Semaphore(0)
        self.allow_sem = threading.Semaphore(0)
        self.raise_next = 0
        real_verify = self.store.verify
        real_events = self.store.events

        def gate():
            self.entered.release()
            assert self.allow_sem.acquire(timeout=60)
            if self.raise_next:
                self.raise_next -= 1
                raise RuntimeError("synthetic failure")

        def verify():
            gate()
            return real_verify()

        def events(**kw):
            gate()
            return real_events(**kw)

        self.store.verify, self.store.events = verify, events
        self.app = create_app(store=self.store)
        self.server, self.thread, self.port = _serve(self.app)
        self.bg: list[threading.Thread] = []

    def start(self, path):
        out: list = []
        t = threading.Thread(target=lambda: out.append(_get(self.port, path, timeout=60)), daemon=True)
        t.start()
        self.bg.append(t)
        return out, t

    def wait_inside(self, n=1):
        for _ in range(n):
            assert self.entered.acquire(timeout=10), "a heavy request never reached the store"

    def allow(self, n=1):
        for _ in range(n):
            self.allow_sem.release()

    def close(self):
        self.allow(50)
        for t in self.bg:
            t.join(30)
        self.server.should_exit = True
        self.thread.join(30)
        for lane in self.app.state.lanes.values():
            lane.shutdown(wait=False, cancel_futures=True)


@pytest.fixture()
def make(tmp_path, monkeypatch):
    made: list[Stack] = []

    def build(**kw):
        s = Stack(tmp_path, monkeypatch, **kw)
        made.append(s)
        return s

    yield build
    for s in made:
        s.close()


def _assert_exactly_one_runs(s: Stack, path="/verify"):
    """Hold one request inside the store; a second one (either whole-ledger form) must be refused 503 at once, and
    nothing else may have entered the store. Then let the held one finish."""
    out, t = s.start(path)
    s.wait_inside()
    for second in ("/verify", "/events"):
        status, body = _get(s.port, second, timeout=5)
        assert status == 503, (second, status)
        assert json.loads(body)["detail"].startswith("ledger busy:")
    assert not s.entered.acquire(timeout=0.3), "a second whole-ledger read entered the store while one was in flight"
    s.allow()
    t.join(30)
    assert out and out[0][0] == 200, out
    assert s.app.state.heavy.inflight == 0


@pytest.mark.parametrize("path", ["/verify", "/events"])
def test_the_limit_still_holds_after_earlier_requests_finished(make, path):
    s = make()
    for _ in range(3):
        _assert_exactly_one_runs(s, path)
        # an earlier request has now finished; run one more to completion on its own, then hold again
        s.allow()
        assert _get(s.port, path, timeout=30)[0] == 200
        s.wait_inside()  # that request entered the store; consume its count
        assert s.app.state.heavy.inflight == 0


@pytest.mark.parametrize("path", ["/verify", "/events"])
def test_the_limit_still_holds_after_an_earlier_request_raised(make, path):
    s = make()
    for _ in range(3):
        s.raise_next = 1
        s.allow()
        assert _get(s.port, path, timeout=30)[0] == 500
        s.wait_inside()
        assert s.app.state.heavy.inflight == 0
        _assert_exactly_one_runs(s, path)


def test_a_finished_request_frees_exactly_one_slot_at_width_two(make, monkeypatch):
    """Over-release: with width 2, one of two running requests ending frees ONE slot, not both."""
    monkeypatch.setenv("FIELD_LEDGER_READ_CONCURRENCY", "2")  # the read lane must also run two at once
    s = make(width=2)
    a, ta = s.start("/verify")
    b, tb = s.start("/verify")
    s.wait_inside(2)
    assert _get(s.port, "/verify", timeout=5)[0] == 503
    s.allow()  # exactly one of the two finishes
    deadline = time.monotonic() + 10
    while s.app.state.heavy.inflight != 1 and time.monotonic() < deadline:
        time.sleep(0.02)
    assert s.app.state.heavy.inflight == 1
    c, tc = s.start("/verify")  # takes the one freed slot
    s.wait_inside()
    status, _ = _get(s.port, "/verify", timeout=5)
    assert status == 503, "two slots were freed by one finished request"
    assert not s.entered.acquire(timeout=0.3)
    s.allow(2)
    for t in (ta, tb, tc):
        t.join(30)
    assert s.app.state.heavy.inflight == 0


@pytest.mark.parametrize("qs", ["agent_id=a1", "agent_id=a1&limit=5"])
def test_an_agent_id_only_read_is_not_gated(make, qs):
    """While a whole-ledger read is held, an agent_id read is not refused 503 by admission: it waits its turn on the read
    lane behind the held read (so nothing answers in the first second), then answers 200 once that one ends."""
    s = make()
    s.start("/verify")
    s.wait_inside()
    out, t = s.start("/events?" + qs)
    time.sleep(1.0)
    assert out == [], f"an agent_id-only read was answered while the heavy one was held (503 = gated): {out}"
    assert s.app.state.heavy.inflight == 1
    s.allow(2)
    t.join(30)
    assert out and out[0][0] == 200, out


def test_an_agent_id_only_read_does_not_take_the_slot(make):
    s = make()
    out, t = s.start("/events?agent_id=a1")
    s.wait_inside()
    assert s.app.state.heavy.inflight == 0
    s.allow()
    t.join(30)
    assert out and out[0][0] == 200
