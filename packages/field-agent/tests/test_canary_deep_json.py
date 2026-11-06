"""S6-8: deeply nested JSON must not escape the canary as RecursionError.

A body inside MAX_BODY_BYTES made of '[' nests deeper than the interpreter's recursion limit; json.loads raises
RecursionError, which is not a ValueError. In do_POST that happened before state.halt, so the halt was not performed
(the one thing the endpoint exists to do); in urllib_call it made x3-check die instead of reporting a FAIL. FieldClient
already catches both (field_client.py)."""

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from field_agent import canary as canary_mod
from field_agent.canary import ORIGIN_HEADER, ORIGIN_VALUE, CanaryAgent

DEEP = b"[" * 60_000
assert len(DEEP) < canary_mod.MAX_BODY_BYTES


@pytest.fixture()
def running(monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    agent = CanaryAgent("canary-gb10", host="127.0.0.1", port=0, work_every=0.01)
    thread = threading.Thread(target=agent.serve_forever, daemon=True)
    thread.start()
    try:
        yield SimpleNamespace(agent=agent, base=f"http://127.0.0.1:{agent.port}")
    finally:
        agent.shutdown()
        thread.join(timeout=5)


def test_a_deeply_nested_halt_body_still_halts_the_canary(running):
    req = urllib.request.Request(f"{running.base}/halt", data=DEEP, method="POST",
                                 headers={ORIGIN_HEADER: ORIGIN_VALUE, "Content-Type": "application/json"})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=10) as resp:
        body = json.loads(resp.read())
        assert resp.status == 200
    assert body["halted"] is True and body["nonce"] is None


def test_urllib_call_reports_a_deeply_nested_reply_as_non_json_bytes():
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(DEEP)))
            self.end_headers()
            self.wfile.write(DEEP)

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        got = canary_mod.urllib_call("GET", f"http://127.0.0.1:{srv.server_address[1]}/x")
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)
    assert got == (200, {"non_json_bytes": 60_000})
