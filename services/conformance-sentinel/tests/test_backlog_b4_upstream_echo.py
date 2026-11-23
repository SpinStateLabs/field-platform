"""Backlog B4 (roley.reviewer B-SENTINEL-UPSTREAM-ECHO): the conformance-sentinel CLI never prints the raw upstream
body, ``field_core.errors.upstream_error`` never logs it, and the sentinel's own httpx clients pin
``follow_redirects=False`` explicitly. Nothing here touches a network. Every value is made up."""
from __future__ import annotations

import json
import logging

import httpx
import pytest
from typer.testing import CliRunner

from conformance_sentinel import cli as cli_mod
from conformance_sentinel import headers
from field_core.errors import upstream_error

MARK = "ECHO-b4-7c21"          # stands in for a value an upstream echoes back (a header, a secret)
runner = CliRunner()
ARGS = ["check", "invoicing-agent", "draft invoices", "--token-id", "t1"]


class Resp:
    def __init__(self, status=200, body=None, text=None):
        self.status_code = status
        self._body = body
        self.text = text if text is not None else json.dumps(body)
        self.content = self.text.encode("utf-8")

    def json(self):
        return self._body


class Stub:
    def __init__(self, resp):
        self.resp, self.calls = resp, []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        return self.resp


@pytest.fixture()
def run(monkeypatch):
    monkeypatch.setenv("FIELD_SENTINEL_URL", "http://127.0.0.1:8004")

    def go(resp):
        stub = Stub(resp)
        monkeypatch.setattr(cli_mod, "httpx", stub)
        return runner.invoke(cli_mod.app, ARGS), stub
    return go


@pytest.mark.parametrize("status", [401, 403, 500, 502, 503])
def test_check_non_200_prints_the_status_only(run, status):
    r, _ = run(Resp(status=status, text=f"<html>{MARK} x-field-secret: {MARK}</html>"))
    assert r.exit_code == 1
    assert MARK not in r.output and "<html>" not in r.output
    assert f"returned {status}" in r.output and r.output.count("\n") == 1


def test_check_200_prints_the_parsed_verdict_not_the_raw_body(run):
    raw = '{"decision": "ALLOW", "clause_id": null, "note": "\\u001b[31mred"}' + " " * 50 + "\n\n"
    r, _ = run(Resp(body={"decision": "ALLOW", "clause_id": None, "note": "\x1b[31mred"}, text=raw))
    assert r.exit_code == 0
    assert "\x1b" not in r.output                       # ensure_ascii re-serialisation escapes control characters
    assert json.loads(r.output) == {"decision": "ALLOW", "clause_id": None, "note": "\x1b[31mred"}


def test_check_post_pins_follow_redirects_false(run):
    _, stub = run(Resp(body={"decision": "ALLOW"}))
    assert stub.calls[0][1]["follow_redirects"] is False


def test_upstream_error_never_logs_the_body(caplog):
    with caplog.at_level(logging.DEBUG, logger="field_core.upstream"):
        msg = upstream_error(Resp(status=502, text=MARK * 10), "sentinel /check")
    assert msg == "sentinel /check returned 502"
    assert MARK not in caplog.text and "body withheld (120 bytes)" in caplog.text


def test_upstream_error_survives_a_reply_without_content(caplog):
    class Bare:
        status_code = 500
        text = MARK

    with caplog.at_level(logging.DEBUG, logger="field_core.upstream"):
        assert upstream_error(Bare(), "x") == "x returned 500"
    assert MARK not in caplog.text and "unknown" in caplog.text


@pytest.mark.parametrize("make", [headers.sentinel_client, headers.registry_client, headers.delegation_client])
def test_every_headers_client_refuses_to_follow_a_redirect(make):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://elsewhere.invalid/steal"})

    with make("http://127.0.0.1:9", transport=httpx.MockTransport(handler)) as client:
        assert client.follow_redirects is False
        r = client.get("/health")
    assert r.status_code == 302 and seen == ["http://127.0.0.1:9/health"]   # the Location was not followed


def test_the_headers_source_sets_follow_redirects_false_on_every_client():
    import inspect
    src = inspect.getsource(headers)
    assert src.count("follow_redirects=False)") == 3
