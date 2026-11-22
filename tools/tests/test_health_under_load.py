"""T6: tools/health_under_load.py is a LOCAL harness (it writes ledger rows) - it must refuse any non-loopback
base URL, ignore the proxy environment, and count a poll as failed exactly as the estate monitor does
(non-200, or 5 s or more)."""
from __future__ import annotations

import importlib.util
import json
import threading
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
