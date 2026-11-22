"""B-GL-heavy-route-inflight: at most ONE whole-ledger request is in flight per ledger process.

A whole-ledger request is GET /verify and a GET /events with no filter (no non-blank limit, agent_id, event_type,
since or until). While one runs, another answers fast with 503 "ledger busy: ..." and a Retry-After header instead of
queueing behind it; /health and appends are never gated and stay answerable. The slot is released when the work ends,
whether it finished, raised, or was cancelled before it started. FIELD_LEDGER_HEAVY_INFLIGHT sets the width (default 1,
0 = no limit, the pre-change queueing).

Every test serves the real app on a loopback port (like test_ledger_c2_hardening) and blocks the store's own verify() /
events() on an Event, so nothing depends on how fast a parse is.
"""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from ledger_c2_support import three_segments
from sealed_ledger.api import create_app

ENV = "FIELD_LEDGER_HEAVY_INFLIGHT"
RETRY_ENV = "FIELD_LEDGER_HEAVY_RETRY_AFTER_S"


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


def _req(port, method, path, body=None, timeout=10.0):
    t0 = time.monotonic()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        headers = {"content-type": "application/json"} if body is not None else {}
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        return time.monotonic() - t0, resp.status, data, {k.lower(): v for k, v in resp.getheaders()}
    finally:
        conn.close()


class Stack:
    """A served ledger whose verify()/events() block until ``release`` is set; ``entered`` counts the calls inside."""

    def __init__(self, tmp_path, monkeypatch, width=None, retry_after=None):
        if width is not None:
            monkeypatch.setenv(ENV, str(width))
        if retry_after is not None:
            monkeypatch.setenv(RETRY_ENV, str(retry_after))
        self.store, _, _ = three_segments(tmp_path / "ledger")
        self.entered = threading.Semaphore(0)
        self.release = threading.Event()
        real_verify, real_events = self.store.verify, self.store.events

        def verify():
            self.entered.release()
            assert self.release.wait(60)
            return real_verify()

        def events(**kw):
            self.entered.release()
            assert self.release.wait(60)
            return real_events(**kw)

        self.store.verify, self.store.events = verify, events
        self.app = create_app(store=self.store)
        self.server, self.thread, self.port = _serve(self.app)
        self.bg: list[threading.Thread] = []

    def start(self, path):
        out: list = []
        t = threading.Thread(target=lambda: out.append(_req(self.port, "GET", path, timeout=60)), daemon=True)
        t.start()
        self.bg.append(t)
        return out

    def wait_inside(self, n=1):
        for _ in range(n):
            assert self.entered.acquire(timeout=10), "a heavy request never reached the store"

    def close(self):
        self.release.set()
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


def test_a_second_verify_while_one_runs_is_refused_fast_with_retry_after(make):
    s = make()
    first = s.start("/verify")
    s.wait_inside()
    dt, status, body, headers = _req(s.port, "GET", "/verify", timeout=5)
    assert status == 503 and dt < 2.0, (status, dt)
    assert json.loads(body)["detail"].startswith("ledger busy:")
    assert headers.get("retry-after") == "5"
    s.release.set()
    s.bg[0].join(30)
    assert first and first[0][1] == 200 and json.loads(first[0][2])["ok"] is True


@pytest.mark.parametrize("held,second", [("/verify", "/events"), ("/events", "/verify"), ("/events", "/events"),
                                         ("/verify", "/events?event_type=")])
def test_the_slot_is_shared_by_verify_and_unfiltered_events(make, held, second):
    s = make()
    s.start(held)
    s.wait_inside()
    dt, status, body, headers = _req(s.port, "GET", second, timeout=5)
    assert status == 503 and dt < 2.0 and "retry-after" in headers, (status, dt)


def test_a_filtered_events_read_is_not_refused(make):
    """A filtered read is not a whole-ledger request: it is never answered 503 by the admission check (here it
    waits its turn on the read lane behind the held verify, then answers 200)."""
    s = make()
    s.start("/verify")
    s.wait_inside()
    out: list = []
    t = threading.Thread(target=lambda: out.append(_req(s.port, "GET", "/events?limit=1", timeout=60)), daemon=True)
    t.start()
    time.sleep(1.0)
    assert out == [], "a filtered read must not be refused (it was answered while the heavy one was still held)"
    s.release.set()
    t.join(30)
    assert out and out[0][1] == 200


def test_health_and_appends_stay_answerable_while_one_runs_and_another_is_refused(make):
    s = make()
    s.start("/verify")
    s.wait_inside()
    assert _req(s.port, "GET", "/verify", timeout=5)[1] == 503
    for _ in range(3):
        dt, status, body, _ = _req(s.port, "GET", "/health", timeout=3)
        assert status == 200 and dt < 2.0
    dt, status, body, _ = _req(s.port, "POST", "/events", body={"event_type": "while.heavy.runs"}, timeout=5)
    assert status == 201 and dt < 5.0


def test_the_slot_is_free_again_after_the_request_ends(make):
    s = make()
    s.release.set()
    for _ in range(3):
        assert _req(s.port, "GET", "/verify", timeout=30)[1] == 200


def test_the_slot_is_free_again_after_the_request_raised(make):
    s = make()
    s.release.set()
    boom = {"on": True}
    real = s.store.verify

    def verify():
        if boom["on"]:
            raise RuntimeError("synthetic failure")
        return real()

    s.store.verify = verify
    assert _req(s.port, "GET", "/verify", timeout=30)[1] == 500
    boom["on"] = False
    assert _req(s.port, "GET", "/verify", timeout=30)[1] == 200


def test_a_job_cancelled_before_it_started_gives_its_slot_back(tmp_path):
    """The slot is released by a done-callback on the executor future, so a future cancelled while still queued
    (a client that disconnected) cannot leak it."""
    s, _, _ = three_segments(tmp_path / "ledger")
    app = create_app(store=s)
    admission = app.state.heavy
    blocker, gate = ThreadPoolExecutor(1), threading.Event()
    blocker.submit(gate.wait, 30)                      # the only worker is busy
    assert admission.try_acquire()
    fut = admission.submit(blocker, lambda: None)      # queued behind the blocker
    assert admission.inflight == 1
    assert fut.cancel()
    assert admission.inflight == 0
    gate.set()
    blocker.shutdown(wait=True)
    for lane in app.state.lanes.values():
        lane.shutdown(wait=False)


@pytest.mark.parametrize("width", [2, 0])
def test_the_width_is_configurable_and_zero_means_no_limit(make, width):
    s = make(width=width)
    s.start("/verify")
    s.wait_inside()
    out = s.start("/verify")
    time.sleep(0.5)
    assert out == [], "with room for another heavy request the second must be admitted (it queues, not 503)"
    s.release.set()
    for t in s.bg:
        t.join(30)
    assert out[0][1] == 200


def test_width_two_refuses_the_third(make):
    s = make(width=2)
    s.start("/verify")
    s.wait_inside()
    s.start("/verify")
    time.sleep(0.5)
    assert _req(s.port, "GET", "/verify", timeout=5)[1] == 503


@pytest.mark.parametrize("raw", ["abc", "-1", "", "1.5", "9" * 5000])
def test_a_bad_width_is_the_default_one(tmp_path, monkeypatch, raw):
    monkeypatch.setenv(ENV, raw)
    s, _, _ = three_segments(tmp_path / "ledger")
    app = create_app(store=s)
    assert app.state.heavy.limit == 1
    for lane in app.state.lanes.values():
        lane.shutdown(wait=False)


@pytest.mark.parametrize("raw,want", [("30", "30"), ("abc", "5"), ("0", "5"), ("-3", "5"), ("9" * 5000, "5")])
def test_retry_after_is_configurable_and_a_bad_value_is_five(make, raw, want):
    s = make(retry_after=raw)
    s.start("/verify")
    s.wait_inside()
    _, status, _, headers = _req(s.port, "GET", "/verify", timeout=5)
    assert status == 503 and headers.get("retry-after") == want


def test_a_client_that_leaves_while_the_work_runs_does_not_free_the_slot(make):
    """The slot belongs to the WORK: a client that drops its connection mid-request does not let a second heavy
    request in while the first thread is still running; it is free again only after that thread ends."""
    s = make()
    sock = socket.create_connection(("127.0.0.1", s.port), timeout=10)
    sock.sendall(b"GET /verify HTTP/1.1"+chr(13).encode()+chr(10).encode()+b"Host: x"+chr(13).encode()+chr(10).encode()+b"Connection: close"+chr(13).encode()+chr(10).encode()+chr(13).encode()+chr(10).encode())
    s.wait_inside()
    sock.close()                                        # the client leaves; the worker is still blocked
    time.sleep(1.0)
    assert _req(s.port, "GET", "/verify", timeout=5)[1] == 503
    s.release.set()
    deadline = time.monotonic() + 30
    status = 503
    while status == 503 and time.monotonic() < deadline:
        time.sleep(0.2)
        status = _req(s.port, "GET", "/verify", timeout=30)[1]
    assert status == 200


def test_the_slot_is_given_back_when_the_executor_refuses_the_work(tmp_path):
    """Review (mutant 19): when executor.submit raises (a pool shut down), the slot taken by try_acquire is released."""
    from sealed_ledger.api import HeavyAdmission

    admission = HeavyAdmission(1)
    dead = ThreadPoolExecutor(1)
    dead.shutdown()
    assert admission.try_acquire()
    with pytest.raises(RuntimeError):
        admission.submit(dead, lambda: None)
    assert admission.inflight == 0 and admission.try_acquire()


def test_the_refusal_detail_names_the_wait(make):
    """Review (mutant 16): the detail tells the caller how long to wait, matching the header."""
    s = make(retry_after=7)
    s.start("/verify")
    s.wait_inside()
    _, status, body, headers = _req(s.port, "GET", "/verify", timeout=5)
    assert status == 503 and headers.get("retry-after") == "7"
    assert json.loads(body)["detail"] == "ledger busy: a whole-ledger request is already in flight; retry after 7 s"


@pytest.mark.parametrize("raw", ["٣", "３", "+2", " 2x"])
def test_only_ascii_digits_count_as_a_width(tmp_path, monkeypatch, raw):
    monkeypatch.setenv(ENV, raw)
    from sealed_ledger.api import heavy_inflight_limit

    assert heavy_inflight_limit() == 1


@pytest.mark.parametrize("raw,want", [("٣", "5"), ("３", "5"), ("3", "3")])
def test_only_ascii_digits_count_as_a_retry_after(monkeypatch, raw, want):
    monkeypatch.setenv(RETRY_ENV, raw)
    from sealed_ledger.api import heavy_retry_after_s

    assert str(heavy_retry_after_s()) == want


# ------------------------------------------------- roley.reviewer's conditions on 66b9c95 (C2)

def test_admission_is_atomic_under_contention():
    """Mutant M4b (the check and the increment not under one lock, with a gap between them): with 16 threads released
    together at a tiny switch interval exactly one acquire may succeed, round after round."""
    import sys

    from sealed_ledger.api import HeavyAdmission

    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        for _ in range(150):
            admission = HeavyAdmission(1)
            barrier = threading.Barrier(16)
            got: list[bool] = []

            def go():
                barrier.wait()
                got.append(admission.try_acquire())

            threads = [threading.Thread(target=go) for _ in range(16)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(10)
            assert sum(got) == 1 and admission.inflight == 1, (sum(got), admission.inflight)
    finally:
        sys.setswitchinterval(old)


def test_health_and_an_append_do_not_take_the_slot_so_a_verify_afterwards_is_200(make):
    """Mutant M18 (/health takes the slot while it is free and keeps it): after /health and an append with nothing
    heavy running, the next /verify is admitted."""
    s = make()
    s.release.set()
    assert _req(s.port, "GET", "/health", timeout=5)[1] == 200
    assert _req(s.port, "POST", "/events", body={"event_type": "while.free"}, timeout=10)[1] == 201
    assert s.app.state.heavy.inflight == 0
    assert _req(s.port, "GET", "/verify", timeout=30)[1] == 200


def test_a_whitespace_padded_env_value_counts(monkeypatch):
    """Mutant M26 (the value is not stripped): " 2 " is 2 and " 7 " is 7, as for every other numeric env in this repo."""
    from sealed_ledger.api import heavy_inflight_limit, heavy_retry_after_s

    monkeypatch.setenv(ENV, " 2 ")
    monkeypatch.setenv(RETRY_ENV, " 7 ")
    assert heavy_inflight_limit() == 2 and heavy_retry_after_s() == 7


def test_a_since_filtered_read_is_not_gated_and_takes_no_slot(make):
    """What the README states: a since/until read is a whole-ledger read that never takes the slot (so it is ungated)."""
    s = make()
    s.start("/verify")
    s.wait_inside()
    out: list = []
    t = threading.Thread(target=lambda: out.append(_req(s.port, "GET", "/events?since=1970-01-01T00:00:00Z",
                                                        timeout=60)), daemon=True)
    t.start()
    time.sleep(1.0)
    assert out == [], "a since-filtered read must not be refused (it waits its turn on the read lane instead)"
    assert s.app.state.heavy.inflight == 1                              # only the held /verify has the slot
    s.release.set()
    t.join(30)
    assert out and out[0][1] == 200
