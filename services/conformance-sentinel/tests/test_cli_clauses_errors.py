"""S9-23: ``sentinel clauses`` checks the answer like ``check`` does. A 401 {detail}, a 5xx HTML body, a JSON list, a
non-string value or a transport error is exit 1 with one line on stderr, never a traceback, never a printed pseudo-clause
and never exit 0. The happy-path format (``cid`` padded to 22, a space, the text) is unchanged. Every value is made up."""
from __future__ import annotations

import httpx
import pytest
from typer.testing import CliRunner

from conformance_sentinel import cli

runner = CliRunner()
MARK = "MARKER-5d02"


def serve(monkeypatch, handler):
    real = httpx.Client

    def get(url, **kw):
        with real(transport=httpx.MockTransport(handler)) as c:
            return c.get(url, **{k: v for k, v in kw.items() if k in ("headers", "timeout")})

    monkeypatch.setattr(cli.httpx, "get", get)


def run():
    res = runner.invoke(cli.app, ["clauses"])
    assert "Traceback" not in res.output
    assert res.exception is None or isinstance(res.exception, SystemExit), repr(res.exception)
    return res


def test_a_200_object_prints_cid_text_lines_and_exits_0(monkeypatch):
    serve(monkeypatch, lambda r: httpx.Response(200, json={"D.scope": "scope text", "E.spend_cap": "cap text"}))
    res = run()
    assert res.exit_code == 0
    assert res.output.splitlines() == [f"{'D.scope':22s} scope text", f"{'E.spend_cap':22s} cap text"]


def test_an_empty_object_is_a_valid_empty_list(monkeypatch):
    serve(monkeypatch, lambda r: httpx.Response(200, json={}))
    res = run()
    assert res.exit_code == 0 and res.output == ""


@pytest.mark.parametrize("response", [
    httpx.Response(401, json={"detail": f"missing perimeter secret {MARK}"}),
    httpx.Response(403, json={"detail": MARK}),
    httpx.Response(502, text=f"<html>Bad gateway {MARK}</html>"),
    httpx.Response(500, json={"detail": MARK}),
], ids=["401", "403", "502-html", "500"])
def test_a_non_200_is_exit_1_with_the_status_and_no_body(monkeypatch, response):
    serve(monkeypatch, lambda r: response)
    res = run()
    assert res.exit_code == 1
    assert f"sentinel /clauses returned {response.status_code}" in res.output
    assert MARK not in res.output and "detail" not in res.output


@pytest.mark.parametrize("response", [
    httpx.Response(200, json=[MARK, "x"]),
    httpx.Response(200, json=MARK),
    httpx.Response(200, json=None),
    httpx.Response(200, json={"D.scope": 5}),
    httpx.Response(200, json={"D.scope": None}),
    httpx.Response(200, json={"D.scope": {"nested": MARK}}),
    httpx.Response(200, text=f"not json {MARK}"),
    httpx.Response(200, content=b""),
], ids=["list", "string", "null", "int-value", "null-value", "dict-value", "not-json", "empty-body"])
def test_a_200_of_the_wrong_shape_is_exit_1_and_prints_nothing_from_it(monkeypatch, response):
    serve(monkeypatch, lambda r: response)
    res = run()
    assert res.exit_code == 1 and "error: unexpected /clauses answer" in res.output
    assert MARK not in res.output


def test_a_transport_error_is_exit_1_with_the_class_only(monkeypatch):
    def handler(request):
        raise httpx.ConnectError(f"cannot reach {request.url} {MARK}")

    serve(monkeypatch, handler)
    res = run()
    assert res.exit_code == 1 and "error: sentinel unreachable (ConnectError)" in res.output
    assert MARK not in res.output and "127.0.0.1" not in res.output
