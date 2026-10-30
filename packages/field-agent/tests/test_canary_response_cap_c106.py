"""C-106 (reviewer C-102 F-C102-3): ``canary.urllib_call`` reads a reply with a bound.

``FieldClient`` refuses a reply larger than ``MAX_RESPONSE_BYTES`` (field_client.py); the canary's own
``urllib_call`` used ``resp.read()`` and ``exc.read()`` with no bound, so a hostile or broken service
(or anything on the path) could make the x3-check process hold an arbitrarily large body in memory.
Same rule here: ask for at most the cap plus one byte; an over-cap reply is an answer with no body
(``{"response_too_large": <cap>}``), never parsed; exactly the cap is read.
"""

from __future__ import annotations

import io
import json
import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from field_agent import canary as canary_mod

CAP = canary_mod.MAX_RESPONSE_BYTES
OK = json.dumps({"ok": True}).encode()


@pytest.fixture()
def reply():
    """A server answering every request with (status, bytes) taken from the returned list."""
    state = {"status": 200, "body": OK}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _answer(self):
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(state["body"])))
            self.end_headers()
            self.wfile.write(state["body"])

        do_GET = do_POST = _answer

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        yield state, f"http://127.0.0.1:{srv.server_address[1]}"
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)


def test_the_cap_is_the_same_as_the_field_client_cap():
    from field_agent import field_client

    assert CAP == field_client.MAX_RESPONSE_BYTES == 64 * 1024


def test_a_reply_of_exactly_the_cap_is_read_and_parsed(reply):
    state, base = reply
    state["body"] = OK + b" " * (CAP - len(OK))
    assert canary_mod.urllib_call("GET", f"{base}/x") == (200, {"ok": True})


def test_a_reply_one_byte_over_the_cap_is_refused_with_no_body(reply):
    state, base = reply
    state["body"] = OK + b" " * (CAP + 1 - len(OK))
    assert canary_mod.urllib_call("GET", f"{base}/x") == (200, {"response_too_large": CAP})


def test_valid_json_followed_by_padding_beyond_the_cap_is_not_parsed(reply):
    state, base = reply
    state["body"] = OK + b" " * (CAP + 500)
    status, body = canary_mod.urllib_call("GET", f"{base}/x")
    assert body == {"response_too_large": CAP} and "ok" not in body


def test_an_error_status_with_an_oversize_body_is_bounded_too(reply):
    state, base = reply
    state["status"], state["body"] = 500, b"x" * (CAP + 10)
    assert canary_mod.urllib_call("POST", f"{base}/x", {}) == (500, {"response_too_large": CAP})


def test_an_error_status_with_a_small_body_still_reports_it(reply):
    state, base = reply
    state["status"], state["body"] = 409, OK
    assert canary_mod.urllib_call("POST", f"{base}/x", {}) == (409, {"ok": True})


def test_the_read_is_asked_for_at_most_the_cap_plus_one(monkeypatch):
    asked: list = []

    class _Resp:
        status = 200

        def read(self, amt=None):
            asked.append(amt)
            return OK

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    class _Opener:
        def open(self, req, timeout=None):
            return _Resp()

    monkeypatch.setattr(canary_mod, "_OPENER", _Opener())
    assert canary_mod.urllib_call("GET", "http://127.0.0.1:9/x") == (200, {"ok": True})
    assert asked == [CAP + 1]


def test_the_error_body_read_is_asked_for_at_most_the_cap_plus_one(monkeypatch):
    asked: list = []

    class _Body(io.BytesIO):
        def read(self, amt=-1):
            asked.append(amt)
            return super().read(amt)

    class _Opener:
        def open(self, req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 500, "boom", {}, _Body(OK))

    monkeypatch.setattr(canary_mod, "_OPENER", _Opener())
    assert canary_mod.urllib_call("GET", "http://127.0.0.1:9/x") == (500, {"ok": True})
    assert asked == [CAP + 1]


def test_the_http_error_is_closed_after_its_body_is_read(monkeypatch):
    """Reviewer C-704 F-C704-3: the error response is closed, as FieldClient does."""
    closed: list = []

    class _Body(io.BytesIO):
        def close(self):
            closed.append(1)
            super().close()

    class _Opener:
        def open(self, req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 500, "boom", {}, _Body(OK))

    monkeypatch.setattr(canary_mod, "_OPENER", _Opener())
    assert canary_mod.urllib_call("GET", "http://127.0.0.1:9/x") == (500, {"ok": True})
    assert closed == [1]


def test_the_http_error_is_closed_even_when_the_read_fails(monkeypatch):
    closed: list = []

    class _Body(io.BytesIO):
        def read(self, amt=-1):
            raise OSError("reset")

        def close(self):
            closed.append(1)
            super().close()

    class _Opener:
        def open(self, req, timeout=None):
            raise urllib.error.HTTPError(req.full_url, 500, "boom", {}, _Body(b""))

    monkeypatch.setattr(canary_mod, "_OPENER", _Opener())
    status, body = canary_mod.urllib_call("GET", "http://127.0.0.1:9/x")
    assert status == 0 and body == {"transport_error": "OSError"} and closed == [1]


def test_the_marker_shape_is_documented_where_the_function_is_described():
    doc = canary_mod.urllib_call.__doc__
    assert "response_too_large" in doc and "non_json_bytes" in doc and "transport_error" in doc
