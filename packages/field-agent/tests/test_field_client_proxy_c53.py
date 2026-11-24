"""C-53 (reviewer C-41 finding 1, proven; finding 2): FieldClient must never send x-field-auth
to an environment proxy, and must refuse a reply larger than MAX_RESPONSE_BYTES.

The module-level opener is built at import, so the proxy variables are set BEFORE import in a
subprocess. A loopback listener plays the proxy; another plays the estate."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from field_agent import field_client as fc

SECRET = "fake-shared-secret-c53"


class _Server:
    def __init__(self, reply=b'{"decision": "ALLOW"}'):
        self.requests: list[dict] = []
        outer = self

        class H(BaseHTTPRequestHandler):
            def _do(self):
                n = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(n)
                outer.requests.append({"path": self.path, "headers": dict(self.headers)})
                self.send_response(200)
                self.send_header("Content-Length", str(len(reply)))
                self.end_headers()
                self.wfile.write(reply)

            do_POST = do_GET = _do

            def log_message(self, *a):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.server.daemon_threads = True
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05},
                         daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def test_the_default_opener_ignores_a_proxy_set_before_import():
    estate, proxy = _Server(), _Server()
    try:
        env = dict(os.environ)
        env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
        for k in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
            env[k] = proxy.base
        env.pop("no_proxy", None)
        env.pop("NO_PROXY", None)
        code = "; ".join([
            "from field_agent.field_client import FieldClient",
            f"c = FieldClient({estate.base!r}, 'agent-1', 'tok-1', shared_secret={SECRET!r})",
            "v = c.check('do-a-thing')",
            "print(v.decision)",
        ])
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True,
                             text=True, timeout=60)
        assert out.returncode == 0, out.stderr[-500:]
        assert len(estate.requests) == 1
        got = {k.lower(): v for k, v in estate.requests[0]["headers"].items()}
        assert got.get("x-field-auth") == SECRET
        assert proxy.requests == []                          # the secret never reached the proxy
    finally:
        estate.close()
        proxy.close()


def test_the_default_opener_registers_no_proxy_handler_with_a_proxy_in_the_environment(monkeypatch):
    # an empty ProxyHandler registers no <scheme>_open method, so none is listed
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), fc._NoRedirect())
    assert not [h for h in opener.handlers if isinstance(h, urllib.request.ProxyHandler)]
    assert any(isinstance(h, fc._NoRedirect) for h in fc.NO_REDIRECT.__self__.handlers)


def test_a_reply_larger_than_the_cap_is_refused_and_the_check_blocks():
    big = json.dumps({"decision": "ALLOW", "pad": "x" * (fc.MAX_RESPONSE_BYTES + 100)}).encode()
    estate = _Server(reply=big)
    try:
        c = fc.FieldClient(estate.base, "agent-1", "tok-1", shared_secret=SECRET)
        v = c.check("do-a-thing")
        assert v.decision == "BLOCK"                          # no body: fail closed
    finally:
        estate.close()


def test_a_reply_at_the_cap_is_still_read():
    """C-106 (reviewer C-102): EXACTLY MAX_RESPONSE_BYTES is read, MAX + 1 is refused (the old test sent
    a few bytes, so `>` to `>=` on the size check survived). The padding is whitespace after valid JSON."""
    ok = json.dumps({"decision": "ALLOW"}).encode()
    pad = fc.MAX_RESPONSE_BYTES - len(ok)
    assert pad > 0
    estate = _Server(reply=ok + b" " * pad)
    try:
        c = fc.FieldClient(estate.base, "agent-1", "tok-1", shared_secret=SECRET)
        assert c.check("do-a-thing").decision == "ALLOW"
    finally:
        estate.close()


def test_a_reply_one_byte_over_the_cap_is_refused():
    ok = json.dumps({"decision": "ALLOW"}).encode()
    estate = _Server(reply=ok + b" " * (fc.MAX_RESPONSE_BYTES + 1 - len(ok)))
    try:
        c = fc.FieldClient(estate.base, "agent-1", "tok-1", shared_secret=SECRET)
        assert c.check("do-a-thing").decision == "BLOCK"
    finally:
        estate.close()


def test_a_valid_verdict_followed_by_padding_beyond_the_cap_blocks():
    """C-106: the bytes that fit under the cap are a complete, valid ALLOW. An over-cap reply must
    discard them (`raw = b""`); a client that parsed what it had read would act on an ALLOW it
    refused to finish reading."""
    ok = json.dumps({"decision": "ALLOW"}).encode()
    estate = _Server(reply=ok + b" " * (fc.MAX_RESPONSE_BYTES + 500))
    try:
        c = fc.FieldClient(estate.base, "agent-1", "tok-1", shared_secret=SECRET)
        assert c.check("do-a-thing").decision == "BLOCK"
    finally:
        estate.close()


def test_the_body_is_read_with_a_bound_not_to_the_end():
    """The size check alone is not the bound: an unbounded read() already holds the whole
    reply in memory. The read must be asked for MAX_RESPONSE_BYTES + 1 bytes at most."""
    asked: list = []

    class _Resp:
        status = 200

        def read(self, amt=None):
            asked.append(amt)
            return b'{"decision": "ALLOW"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    c = fc.FieldClient("http://127.0.0.1:9", "agent-1", "tok-1", shared_secret=SECRET,
                       opener=lambda req, timeout=None: _Resp())
    assert c.check("do-a-thing").decision == "ALLOW"
    assert asked == [fc.MAX_RESPONSE_BYTES + 1]
