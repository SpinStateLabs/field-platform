"""B-GL-attest-pack-gate: at most ONE pack build in flight per reporter process; /health never waits.

GET /pack and GET /pack.html each build the whole board pack (16 ledger /events reads and a /verify). While one runs,
another is refused at once with 503 "attestation busy: ..." and a Retry-After header instead of holding a worker thread;
the reporter's own /health stays answerable. The slot is released when the work ends (finished, raised, or cancelled
before it started). FIELD_ATTEST_PACK_INFLIGHT sets the width (default 1, 0 = no limit), FIELD_ATTEST_PACK_RETRY_AFTER_S
the Retry-After (default 10).

Every test serves the real app on a loopback port with a stub engine whose build() blocks on an Event.
"""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from attestation_reporter.api import create_app
from attestation_reporter.engine import BoardPack, Window
from attestation_reporter.window import InvalidWindow

ENV = "FIELD_ATTEST_PACK_INFLIGHT"
RETRY_ENV = "FIELD_ATTEST_PACK_RETRY_AFTER_S"


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


def _req(port, path, timeout=10.0):
    t0 = time.monotonic()
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        data = resp.read()
        return time.monotonic() - t0, resp.status, data, {k.lower(): v for k, v in resp.getheaders()}
    finally:
        conn.close()


class BlockingEngine:
    org = "Test Org"

    def __init__(self):
        self.entered = threading.Semaphore(0)
        self.release = threading.Event()
        self.fail = False
        self.thread_names: list[str] = []

    def build(self, period=None, since=None, until=None):
        if period == "not-a-period":
            raise InvalidWindow("not a period")
        self.thread_names.append(threading.current_thread().name)
        self.entered.release()
        assert self.release.wait(60)
        if self.fail:
            raise RuntimeError("synthetic build failure")
        return BoardPack(org=self.org, period="all-time", window=Window(kind="all-time", note="stub"),
                         generated_at="2026-01-01T00:00:00+00:00", sections=[])


class Stack:
    def __init__(self, monkeypatch, width=None, retry_after=None):
        monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
        if width is not None:
            monkeypatch.setenv(ENV, str(width))
        if retry_after is not None:
            monkeypatch.setenv(RETRY_ENV, str(retry_after))
        self.engine = BlockingEngine()
        self.app = create_app(engine=self.engine)
        self.server, self.thread, self.port = _serve(self.app)
        self.bg: list[threading.Thread] = []

    def start(self, path):
        out: list = []
        t = threading.Thread(target=lambda: out.append(_req(self.port, path, timeout=60)), daemon=True)
        t.start()
        self.bg.append(t)
        return out

    def wait_inside(self):
        assert self.engine.entered.acquire(timeout=10), "a pack build never started"

    def close(self):
        self.engine.release.set()
        for t in self.bg:
            t.join(30)
        self.server.should_exit = True
        self.thread.join(30)
        self.app.state.pack_executor.shutdown(wait=False, cancel_futures=True)


@pytest.fixture()
def make(monkeypatch):
    made: list[Stack] = []

    def build(**kw):
        s = Stack(monkeypatch, **kw)
        made.append(s)
        return s

    yield build
    for s in made:
        s.close()


def test_a_second_pack_while_one_builds_is_refused_fast_with_retry_after(make):
    s = make()
    first = s.start("/pack")
    s.wait_inside()
    dt, status, body, headers = _req(s.port, "/pack", timeout=5)
    assert status == 503 and dt < 2.0, (status, dt)
    assert json.loads(body)["detail"].startswith("attestation busy:")
    assert headers.get("retry-after") == "10"
    s.engine.release.set()
    s.bg[0].join(30)
    assert first and first[0][1] == 200


@pytest.mark.parametrize("held,second", [("/pack", "/pack.html"), ("/pack.html", "/pack"), ("/pack.html", "/pack.html"),
                                         ("/pack", "/pack?period=2026-Q3")])
def test_the_slot_is_shared_by_pack_and_pack_html_whatever_the_query(make, held, second):
    s = make()
    s.start(held)
    s.wait_inside()
    dt, status, _, headers = _req(s.port, second, timeout=5)
    assert status == 503 and dt < 2.0 and "retry-after" in headers


def test_health_stays_answerable_while_one_builds_and_another_is_refused(make):
    s = make()
    s.start("/pack")
    s.wait_inside()
    assert _req(s.port, "/pack", timeout=5)[1] == 503
    for _ in range(5):
        dt, status, body, _ = _req(s.port, "/health", timeout=3)
        assert status == 200 and dt < 1.0
        assert json.loads(body)["service"] == "attestation-reporter"


def test_health_is_not_queued_behind_a_flood_of_pack_requests(make):
    """60 packs at once: one builds, 59 are refused at once; none of them holds a worker thread, so /health is not
    queued behind them (before this the 40-thread shared pool filled with waiting packs)."""
    s = make()
    s.start("/pack")
    s.wait_inside()
    flood: list = []
    threads = [threading.Thread(target=lambda: flood.append(_req(s.port, "/pack", timeout=30)), daemon=True)
               for _ in range(59)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert len(flood) == 59 and all(status == 503 for _, status, _, _ in flood)
    dt, status, _, _ = _req(s.port, "/health", timeout=3)
    assert status == 200 and dt < 1.0


def test_the_slot_is_free_again_after_the_build_ends(make):
    s = make()
    s.engine.release.set()
    for _ in range(3):
        assert _req(s.port, "/pack", timeout=30)[1] == 200


def test_the_slot_is_free_again_after_the_build_raised(make):
    s = make()
    s.engine.release.set()
    s.engine.fail = True
    assert _req(s.port, "/pack", timeout=30)[1] == 500
    s.engine.fail = False
    assert _req(s.port, "/pack", timeout=30)[1] == 200


def test_a_job_cancelled_before_it_started_gives_its_slot_back():
    from attestation_reporter.api import PackAdmission

    admission = PackAdmission(1)
    blocker, gate = ThreadPoolExecutor(1), threading.Event()
    blocker.submit(gate.wait, 30)
    assert admission.try_acquire()
    fut = admission.submit(blocker, lambda: None)
    assert admission.inflight == 1
    assert fut.cancel()
    assert admission.inflight == 0
    gate.set()
    blocker.shutdown(wait=True)


def test_a_client_that_leaves_while_the_build_runs_does_not_free_the_slot(make):
    s = make()
    sock = socket.create_connection(("127.0.0.1", s.port), timeout=10)
    nl = chr(13) + chr(10)
    sock.sendall(("GET /pack HTTP/1.1" + nl + "Host: x" + nl + "Connection: close" + nl + nl).encode())
    s.wait_inside()
    sock.close()
    time.sleep(1.0)
    assert _req(s.port, "/pack", timeout=5)[1] == 503
    s.engine.release.set()
    deadline = time.monotonic() + 30
    status = 503
    while status == 503 and time.monotonic() < deadline:
        time.sleep(0.2)
        status = _req(s.port, "/pack", timeout=30)[1]
    assert status == 200


@pytest.mark.parametrize("width", [2, 0])
def test_the_width_is_configurable_and_zero_means_no_limit(make, width):
    s = make(width=width)
    s.start("/pack")
    s.wait_inside()
    out = s.start("/pack")
    s.wait_inside()                                  # the second build really started: it was admitted, not refused
    s.engine.release.set()
    for t in s.bg:
        t.join(30)
    assert out[0][1] == 200


def test_width_two_refuses_the_third(make):
    s = make(width=2)
    s.start("/pack")
    s.wait_inside()
    s.start("/pack")
    s.wait_inside()
    assert _req(s.port, "/pack", timeout=5)[1] == 503


@pytest.mark.parametrize("raw", ["abc", "-1", "", "1.5", "9" * 5000])
def test_a_bad_width_is_the_default_one(monkeypatch, raw):
    monkeypatch.setenv(ENV, raw)
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    app = create_app(engine=BlockingEngine())
    assert app.state.pack_gate.limit == 1
    app.state.pack_executor.shutdown(wait=False)


@pytest.mark.parametrize("raw,want", [("30", "30"), ("abc", "10"), ("0", "10"), ("-3", "10"), ("9" * 5000, "10")])
def test_retry_after_is_configurable_and_a_bad_value_is_ten(make, raw, want):
    s = make(retry_after=raw)
    s.start("/pack")
    s.wait_inside()
    _, status, _, headers = _req(s.port, "/pack", timeout=5)
    assert status == 503 and headers.get("retry-after") == want


def test_a_bad_window_is_still_422_and_does_not_hold_the_slot(make):
    s = make()
    assert _req(s.port, "/pack?period=not-a-period", timeout=10)[1] == 422
    s.engine.release.set()
    assert _req(s.port, "/pack", timeout=30)[1] == 200


def test_a_pack_build_runs_on_the_reporters_own_pool_not_the_shared_one(make):
    """Review mutant 17: the claim 'builds run on their own pool' is pinned by the worker thread's name."""
    s = make()
    s.engine.release.set()
    assert _req(s.port, "/pack", timeout=30)[1] == 200
    assert s.engine.thread_names and all(n.startswith("attest-pack") for n in s.engine.thread_names), s.engine.thread_names
