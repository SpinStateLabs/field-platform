"""Scout S-2-12, stacked on #546 (the no-proxy, no-redirect opener): `tools/start_role_session.py` also sent
`--budget-cents` as a free string, raised tracebacks on transport errors and a bad reply, and printed up to 400 characters
of the upstream error body. Now: the budget is a validated integer refused before any request (exit 2); a transport
error, a timeout or a reply that is not JSON exits with the exception class name only; an HTTP error exits with the status
and a fixed phrase (the platform rule from C-503: an upstream body is never part of an error message); a reply without a
session id is refused by name. Nothing leaves the machine: local servers and a stubbed opener."""
from __future__ import annotations

import json
import socket
import sys
import urllib.error

import pytest
from test_start_role_session import Server, _load, servers  # noqa: F401  (the #546 harness)

KEY = "synthetic-key-0000"
BODY_MARKER = "UPSTREAM-BODY-MARKER-4471"


@pytest.fixture()
def mod(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    for v in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(v, raising=False)
    return _load()


def run(mod, monkeypatch, *argv):
    monkeypatch.setattr(sys, "argv", ["start_role_session.py", *argv])
    mod.main()


def message(exc: pytest.ExceptionInfo) -> str:
    return str(exc.value)


# ---- (1) the budget ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("bad", ["abc", "", " ", "0", "-5", "1.5", "1e3", "+5", "5 ", "٣", "100000001", "9" * 40, "0x10"])
def test_a_bad_budget_exits_2_naming_the_option_before_any_request(mod, servers, monkeypatch, capsys, bad):  # noqa: F811
    srv = servers(lambda h: (200, {}, b'{"id": "sess_1"}'))
    monkeypatch.setattr(mod, "API_BASE", srv.url)
    with pytest.raises(SystemExit) as e:
        run(mod, monkeypatch, "architect", "name-1", "A", "--budget-cents", bad)
    assert e.value.code == 2
    err = capsys.readouterr().err
    assert "--budget-cents" in err and KEY not in err
    assert srv.requests == []


@pytest.mark.parametrize("good,sent", [("1", "1"), ("100", "100"), ("007", "7"), ("100000000", "100000000")])
def test_a_good_budget_is_sent_as_the_integer_text(mod, servers, monkeypatch, capsys, good, sent):  # noqa: F811
    srv = servers(lambda h: (200, {}, b'{"id": "sess_1"}'))
    monkeypatch.setattr(mod, "API_BASE", srv.url)
    run(mod, monkeypatch, "architect", "name-1", "A", "--budget-cents", good)
    first = json.loads(srv.requests[0]["body"])
    assert first["budget"]["max_list_cost"] == {"amount": sent, "currency": "USD"}


def test_the_default_budget_is_100_cents(mod, servers, monkeypatch, capsys):  # noqa: F811
    srv = servers(lambda h: (200, {}, b'{"id": "sess_1"}'))
    monkeypatch.setattr(mod, "API_BASE", srv.url)
    run(mod, monkeypatch, "red-team", "name-1", "B")
    assert json.loads(srv.requests[0]["body"])["budget"]["max_list_cost"]["amount"] == "100"


# ---- the happy path, so the refusals below are known to be the cause ---------------------------------------------------

def test_a_good_run_creates_the_session_posts_the_event_and_prints_the_id(mod, servers, monkeypatch, capsys):  # noqa: F811
    srv = servers(lambda h: (200, {"content-type": "application/json"}, b'{"id": "sess_9"}'))
    monkeypatch.setattr(mod, "API_BASE", srv.url)
    run(mod, monkeypatch, "architect", "name-1", "A", "--budget-cents", "250")
    assert capsys.readouterr().out.strip() == "sess_9"
    assert [r["path"] for r in srv.requests] == ["/v1/sessions", "/v1/sessions/sess_9/events"]
    h = {k.lower(): v for k, v in srv.requests[0]["headers"].items()}
    assert h["x-api-key"] == KEY
    created = json.loads(srv.requests[0]["body"])
    assert created["metadata"]["role"] == "architect" and created["budget"]["max_list_cost"]["amount"] == "250"


def test_without_a_key_main_sends_nothing(mod, servers, monkeypatch):  # noqa: F811
    srv = servers(lambda h: (200, {}, b'{"id": "s"}'))
    monkeypatch.setattr(mod, "API_BASE", srv.url)
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(SystemExit) as e:
        run(mod, monkeypatch, "architect", "name-1", "A")
    assert "not set" in message(e) and srv.requests == []


# ---- (3) an upstream body is never printed -----------------------------------------------------------------------------

@pytest.mark.parametrize("status", [400, 401, 403, 404, 429, 500, 503])
def test_an_http_error_shows_the_status_and_a_fixed_phrase_never_the_body(mod, servers, monkeypatch, status):  # noqa: F811
    bad = servers(lambda h: (status, {}, f'{{"error": "{BODY_MARKER} {KEY}"}}'.encode()))
    monkeypatch.setattr(mod, "API_BASE", bad.url)
    with pytest.raises(SystemExit) as e:
        run(mod, monkeypatch, "architect", "name-1", "A")
    msg = message(e)
    assert msg.startswith(f"HTTP {status}") and BODY_MARKER not in msg and KEY not in msg
    assert e.value.code not in (0, None)


def test_a_failure_on_the_second_call_also_hides_the_body(mod, servers, monkeypatch):  # noqa: F811
    state = {"n": 0}

    def reply(h):
        state["n"] += 1
        return (200, {}, b'{"id": "sess_1"}') if state["n"] == 1 else (500, {}, BODY_MARKER.encode())

    srv = servers(reply)
    monkeypatch.setattr(mod, "API_BASE", srv.url)
    with pytest.raises(SystemExit) as e:
        run(mod, monkeypatch, "architect", "name-1", "A")
    assert BODY_MARKER not in message(e) and "500" in message(e)


# ---- (2) transport errors and a bad reply exit with the class name only -------------------------------------------------

class _Raises:
    def __init__(self, exc):
        self.exc = exc

    def open(self, *a, **k):
        raise self.exc


@pytest.mark.parametrize("exc", [
    urllib.error.URLError(f"reason with {KEY} and http://secret.example/x"),
    TimeoutError(f"timed out {KEY}"),
    socket.timeout(f"slow {KEY}"),
    ConnectionResetError(f"reset {KEY}"),
    OSError(f"os {KEY}"),
])
def test_a_transport_error_exits_with_the_class_name_only(mod, monkeypatch, exc):
    monkeypatch.setattr(mod, "_OPENER", _Raises(exc))
    with pytest.raises(SystemExit) as e:
        run(mod, monkeypatch, "architect", "name-1", "A")
    msg = message(e)
    assert type(exc).__name__ in msg
    assert KEY not in msg and "secret.example" not in msg and "reason with" not in msg
    assert e.value.code not in (0, None)


def test_a_refused_connection_exits_cleanly(mod, monkeypatch):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]                  # closed again: nothing listens here
    monkeypatch.setattr(mod, "API_BASE", f"http://127.0.0.1:{port}")
    with pytest.raises(SystemExit) as e:
        run(mod, monkeypatch, "architect", "name-1", "A")
    assert "URLError" in message(e) and KEY not in message(e)


@pytest.mark.parametrize("body", [b"not json", b"", b"<html>" + BODY_MARKER.encode() + b"</html>", b"\xff\xfe"])
def test_a_reply_that_is_not_json_exits_with_the_class_name_only(mod, servers, monkeypatch, body):  # noqa: F811
    srv = servers(lambda h: (200, {}, body))
    monkeypatch.setattr(mod, "API_BASE", srv.url)
    with pytest.raises(SystemExit) as e:
        run(mod, monkeypatch, "architect", "name-1", "A")
    msg = message(e)
    assert BODY_MARKER not in msg and KEY not in msg and e.value.code not in (0, None)


# ---- (4) a reply without a session id -----------------------------------------------------------------------------------

@pytest.mark.parametrize("reply", [b"{}", b"[]", b"null", b'{"id": null}', b'{"id": ""}', b'{"id": 5}', b'{"sid": "x"}',
                                   b'"just a string"'])
def test_a_reply_without_a_usable_session_id_is_refused_by_name(mod, servers, monkeypatch, reply):  # noqa: F811
    srv = servers(lambda h: (200, {}, reply))
    monkeypatch.setattr(mod, "API_BASE", srv.url)
    with pytest.raises(SystemExit) as e:
        run(mod, monkeypatch, "architect", "name-1", "A")
    assert "session id" in message(e) and KEY not in message(e)
    assert len(srv.requests) == 1                   # the events call is never made
