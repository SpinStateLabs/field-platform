"""S6-13: ``sentinel check`` exits 0 ONLY for the exact decision ALLOW (BLOCK 1, ESCALATE 2). A decision it does not know,
a missing key, a non-object or non-JSON 200 body is a named line on stderr and exit 1; an unreachable sentinel is one line
and exit 1, never a traceback."""

from __future__ import annotations

import json

import httpx
import pytest
from typer.testing import CliRunner

from conformance_sentinel import cli as cli_mod

runner = CliRunner()
ARGS = ["check", "invoicing-agent", "draft invoices", "--token-id", "t1"]


class Resp:
    def __init__(self, status=200, body=None, text=None):
        self.status_code = status
        self._body = body
        self.text = text if text is not None else json.dumps(body)

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class Stub:
    def __init__(self, outcome):
        self.outcome, self.calls = outcome, []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


@pytest.fixture()
def run(monkeypatch):
    monkeypatch.setenv("FIELD_SENTINEL_URL", "http://127.0.0.1:8004")

    def go(outcome, *extra):
        stub = Stub(outcome)
        monkeypatch.setattr(cli_mod, "httpx", stub)
        r = runner.invoke(cli_mod.app, ARGS + list(extra))
        assert r.exception is None or isinstance(r.exception, SystemExit), repr(r.exception)
        assert "Traceback" not in r.output
        return r, stub
    return go


@pytest.mark.parametrize("decision,code", [("ALLOW", 0), ("BLOCK", 1), ("ESCALATE", 2)])
def test_the_three_decisions_keep_their_exit_codes(run, decision, code):
    r, stub = run(Resp(body={"decision": decision, "clause_id": None}))
    assert r.exit_code == code
    assert decision in r.output                                  # the verdict is still printed
    assert stub.calls[0][0] == "http://127.0.0.1:8004/check"


@pytest.mark.parametrize("body", [{"decision": "banana"}, {"decision": "allow"}, {"decision": "Allow "},
                                  {"decision": ""}, {"decision": None}, {"decision": 1}, {"decision": True},
                                  {"decision": ["ALLOW"]}, {"decision": {"a": 1}}, {}, {"verdict": "ALLOW"},
                                  [], [1, 2], "ALLOW", "x", 7, None, True], ids=repr)
def test_anything_but_a_known_decision_is_exit_1_and_named(run, body):
    r, _ = run(Resp(body=body))
    assert r.exit_code == 1
    assert "error: sentinel answered 200 with" in r.output and "treated as BLOCK" in r.output
    assert r.output.count("\n") == 1                                # one line


def test_a_non_json_200_is_refused(run):
    r, _ = run(Resp(body=ValueError("not json"), text="<html>proxy</html>"))
    assert r.exit_code == 1 and "no readable decision" in r.output
    assert "<html>" not in r.output                                 # the body is not echoed


def test_a_deeply_nested_body_is_refused_not_a_traceback(run):
    r, _ = run(Resp(body=RecursionError("deep"), text="[" * 100_000))
    assert r.exit_code == 1


def test_an_unknown_decision_names_a_short_printable_value_only(run):
    r, _ = run(Resp(body={"decision": "banana"}))
    assert "'banana'" in r.output
    r2, _ = run(Resp(body={"decision": "x" * 500}))
    assert "x" * 100 not in r2.output and "no readable decision" in r2.output
    r3, _ = run(Resp(body={"decision": "A\x1b[31mB"}))  # repr escapes it
    assert "\x1b" not in r3.output


@pytest.mark.parametrize("exc", [httpx.ConnectError("refused"), httpx.ConnectTimeout("t"), httpx.ReadTimeout("t"),
                                 httpx.RemoteProtocolError("bad"), httpx.UnsupportedProtocol("x"),
                                 httpx.InvalidURL("bad")], ids=lambda e: type(e).__name__)
def test_an_unreachable_sentinel_is_one_line_exit_1(run, exc):
    r, _ = run(exc)
    assert r.exit_code == 1
    assert f"error: sentinel unreachable ({type(exc).__name__})" in r.output and r.output.count("\n") == 1


def test_a_non_200_status_is_still_exit_1(run):
    r, _ = run(Resp(status=503, body={"detail": "down"}))
    assert r.exit_code == 1 and "error 503" in r.output
