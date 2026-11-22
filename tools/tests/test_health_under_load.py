"""T6: tools/health_under_load.py is a LOCAL harness (it writes ledger rows) - it must refuse any non-loopback
base URL, ignore the proxy environment, and count a poll as failed exactly as the estate monitor does
(non-200, or 5 s or more)."""
from __future__ import annotations

import importlib.util
import json
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "health_under_load", Path(__file__).resolve().parents[1] / "health_under_load.py")
hul = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(hul)


class _Stub(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - http.server API
        body = json.dumps({"ok": True}).encode()
        self.send_response(200)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.mark.parametrize("base", ["http://fly-estate.example:8080", "https://10.0.0.5", "http://0.0.0.0:8080",
                                  "ftp://127.0.0.1", "127.0.0.1:8080"])
def test_refuses_non_loopback_base(base):
    with pytest.raises(SystemExit):
        hul.loopback_base(base)
    with pytest.raises(SystemExit):
        hul.main(["seed", "--base", base, "--events", "1"])


@pytest.mark.parametrize("base", ["http://127.0.0.1:8080/", "http://localhost:8080", "http://[::1]:8080"])
def test_accepts_loopback_base(base):
    assert hul.loopback_base(base) == base.rstrip("/")


def test_opener_ignores_proxy_environment(monkeypatch):
    # build_opener(ProxyHandler({})) suppresses the default env-reading ProxyHandler; the empty one has no
    # <scheme>_open method, so no ProxyHandler is registered at all.
    assert not any(isinstance(h, urllib.request.ProxyHandler) for h in hul._OPENER.handlers)
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")  # a dead proxy: a request through it would fail
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        status, _, _ = hul.request("GET", f"http://127.0.0.1:{srv.server_address[1]}/health")
    finally:
        srv.shutdown()
    assert status == 200


def test_console_is_the_bare_health_path():
    assert hul.health_url("http://127.0.0.1:8080", "console") == "http://127.0.0.1:8080/health"
    assert hul.health_url("http://127.0.0.1:8080", "ledger") == "http://127.0.0.1:8080/ledger/health"


def test_summary_counts_slow_and_non_200_as_failed_and_the_longest_run():
    polls = [(0.0, 200, 9.0),  # before the window: idle only
             (1.0, 200, 0.1), (2.0, 200, 5.0), (3.0, "TimeoutError", 5.0), (4.0, 503, 0.01),
             (5.0, 200, 0.2), (6.0, 200, 4.99), (99.0, 200, 7.0)]  # last one after the window
    s = hul.summarize(polls, start=1.0, end=6.0)
    # during: 0.1, 5.0, 5.0, 0.01, 0.2, 4.99 -> median of the middle two (0.2 + 4.99) / 2
    assert s == {"idle_max": 9.0, "n": 6, "failed": 3, "max_consecutive_failed": 3, "p50": 2.595, "max": 5.0}


def test_run_against_a_local_stub_reports_every_prefix():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Stub)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        res = hul.run(base, "/ledger/events", ["ledger", "console"], pre=1.2, post=0.0, container=None)
    finally:
        srv.shutdown()
    assert res["status"] == 200 and set(res["health"]) == {"ledger", "console"}
    assert all(v["failed"] == 0 and v["idle_max"] is not None for v in res["health"].values())
    assert "heavy GET /ledger/events -> 200" in hul.table(res)


# ---- B-1075-TESTS: a deterministic end-to-end stack. The heavy endpoint does not sleep for a guessed time: it
# returns once every polled prefix has had POLLS_IN_WINDOW /health requests ARRIVE while it ran, so the number of
# polls inside the window is fixed by construction, not by timing. Health answers are scripted per prefix.

POLLS_IN_WINDOW = 2
POLL_TIMEOUT = 0.3  # the harness's 5 s, shortened (see _fast_timeout)


class _Fake:
    """Loopback fake: ``plan[prefix](n_in_window)`` -> "ok" | "500" | "drop" | "hang" for each /health request."""

    def __init__(self, plan, extra_hold=None):
        self.plan = plan
        self.in_window = False
        self.counts = {p: 0 for p in plan}  # /health arrivals while the heavy request runs
        self.total = {p: 0 for p in plan}   # every /health arrival
        self.cond = threading.Condition()
        self.hold = extra_hold or {}         # prefix -> Event the FIRST health request blocks on until set
        fake = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                path = self.path
                if path == "/heavy":
                    return fake._heavy(self)
                prefix = "console" if path == "/health" else path.split("/")[1]
                with fake.cond:
                    fake.total[prefix] += 1
                    nth = fake.total[prefix]
                    if fake.in_window:
                        fake.counts[prefix] += 1
                        fake.cond.notify_all()
                    n = fake.counts[prefix]
                act = fake.plan[prefix](n if fake.in_window else 0)
                if nth == 1 and prefix in fake.hold:
                    fake.hold[prefix].wait(10)
                    act = "hang"
                if act == "hang":
                    time.sleep(POLL_TIMEOUT * 3)
                if act == "drop":
                    self.close_connection = True
                    self.connection.close()
                    return
                body = b"{}"
                self.send_response(500 if act == "500" else 200)
                self.send_header("content-length", "2")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        class Quiet(ThreadingHTTPServer):
            daemon_threads = True

            def handle_error(self, request, client_address):  # a client that timed out and left is the point
                pass

        self.srv = Quiet(("127.0.0.1", 0), H)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def _heavy(self, h):
        with self.cond:
            self.in_window = True
            self.cond.notify_all()
            ok = self.cond.wait_for(lambda: all(c >= POLLS_IN_WINDOW for c in self.counts.values()), timeout=20)
            self.in_window = False
        h.send_response(200 if ok else 504)
        h.send_header("content-length", "2")
        h.end_headers()
        h.wfile.write(b"{}")

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def _fast_timeout(monkeypatch):
    """The 5 s poll timeout becomes 0.3 s for /health polls (request()'s default is bound at definition time)."""
    real = hul.request

    def request(method, url, body=None, timeout=900):
        return real(method, url, body, timeout=POLL_TIMEOUT if url.endswith("/health") else timeout)

    monkeypatch.setattr(hul, "request", request)
    monkeypatch.setattr(hul, "HEALTH_TIMEOUT", POLL_TIMEOUT)


def test_e2e_every_poll_failure_kind_is_counted_exactly(_fast_timeout):
    """Polls definitely occur inside the window (POLLS_IN_WINDOW per prefix) and each induced failure kind - a 500,
    a dropped connection, a timeout - is a FAILED poll, not an idle one; the healthy prefix has none."""
    fake = _Fake({"ledger": lambda n: "500" if n else "ok", "registry": lambda n: "drop" if n else "ok",
                  "killswitch": lambda n: "hang" if n else "ok", "console": lambda n: "ok"})
    try:
        res = hul.run(fake.base, "/heavy", ["ledger", "registry", "killswitch", "console"], pre=0.3, post=0.0,
                      container=None)
    finally:
        fake.stop()
    assert res["status"] == 200, res
    h = res["health"]
    assert {p: (v["n"], v["failed"], v["max_consecutive_failed"]) for p, v in h.items()} == {
        "ledger": (2, 2, 2), "registry": (2, 2, 2), "killswitch": (2, 2, 2), "console": (2, 0, 0)}, h
    # the poll that ran before the window was healthy and is idle, never failed
    assert all(v["idle_max"] is not None and v["idle_max"] < POLL_TIMEOUT for v in h.values()), h
    assert h["killswitch"]["max"] >= POLL_TIMEOUT and h["ledger"]["max"] < POLL_TIMEOUT, h
