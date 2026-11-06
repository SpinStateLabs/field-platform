"""S5-21: a transport error or a non-JSON upstream body is a named 502, not a bare 500.
The detail carries the exception class (or the upstream status) only: never the exception text,
the base URL or the key."""

from __future__ import annotations

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from force_gateway import api
from force_gateway.api import real_upstream

KEY = "sk-ant-DUMMY-S521-KEY-0123456789"
HOST = "secret-proxy.internal.example.test"
MSG = {"model": "m", "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(api, "_warned", set())
    monkeypatch.delenv(api.REQUIRE_TLS_ENV, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"https://{HOST}")


def _post_raising(monkeypatch, exc):
    def fake_post(url, json=None, headers=None, timeout=None):
        raise exc
    monkeypatch.setattr(httpx, "post", fake_post)


def _post_returning(monkeypatch, status, content):
    def fake_post(url, json=None, headers=None, timeout=None):
        return httpx.Response(status, content=content, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)


def _assert_clean(detail: str):
    assert KEY not in detail and HOST not in detail


@pytest.mark.parametrize("exc", [
    httpx.ConnectError(f"cannot reach https://{HOST}/v1/messages key={KEY}"),
    httpx.ReadTimeout(f"timed out talking to {HOST}"),
])
def test_a_transport_error_is_a_502_naming_only_the_class(monkeypatch, exc):
    _post_raising(monkeypatch, exc)
    with pytest.raises(HTTPException) as e:
        real_upstream(MSG, {})
    assert e.value.status_code == 502
    assert e.value.detail == f"upstream unreachable: {type(exc).__name__}"
    _assert_clean(e.value.detail)


@pytest.mark.parametrize("status", [200, 502, 503, 401])
def test_a_non_json_body_is_a_502_that_keeps_the_upstream_status(monkeypatch, status):
    _post_returning(monkeypatch, status, b"<html>bad gateway</html>")
    with pytest.raises(HTTPException) as e:
        real_upstream(MSG, {})
    assert e.value.status_code == 502
    assert e.value.detail == f"upstream answered a non-JSON body (status {status})"
    _assert_clean(e.value.detail)


def test_a_json_body_still_passes_through_with_its_status(monkeypatch):
    _post_returning(monkeypatch, 429, b'{"error": {"type": "rate_limit_error"}}')
    assert real_upstream(MSG, {}) == (429, {"error": {"type": "rate_limit_error"}})


@pytest.mark.parametrize("make", [
    lambda mp: _post_raising(mp, httpx.ConnectError(f"boom {HOST}")),
    lambda mp: _post_returning(mp, 200, b"<html>"),
])
def test_the_route_answers_a_named_502_not_a_500(monkeypatch, make):
    make(monkeypatch)
    client = TestClient(api.create_app(), raise_server_exceptions=False)
    r = client.post("/v1/messages", json=MSG, headers={"x-force-passthrough": "1"})
    assert r.status_code != 500
    assert r.status_code == 502, r.text
    _assert_clean(r.text)


# ---- R-PR699-efcf22b conditions: what is SENT is pinned, and a RequestError that is not a TransportError is a 502 ----

def _capture(monkeypatch, status=200, content=b"{}"):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, json=json, headers=headers, timeout=timeout)
        return httpx.Response(status, content=content, request=httpx.Request("POST", url))
    monkeypatch.setattr(httpx, "post", fake_post)
    return seen


def test_the_request_sent_upstream_is_pinned(monkeypatch):
    seen = _capture(monkeypatch)
    real_upstream(MSG, {})
    assert seen["url"] == f"https://{HOST}/v1/messages"
    assert seen["json"] == MSG
    assert seen["headers"] == {"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    assert seen["timeout"] == 120.0


def test_the_callers_anthropic_version_is_forwarded(monkeypatch):
    seen = _capture(monkeypatch)
    real_upstream(MSG, {"anthropic-version": "2099-01-01"})
    assert seen["headers"]["anthropic-version"] == "2099-01-01"


def test_a_trailing_slash_on_the_base_url_is_not_doubled(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"https://{HOST}/")
    seen = _capture(monkeypatch)
    real_upstream(MSG, {})
    assert seen["url"] == f"https://{HOST}/v1/messages"


@pytest.mark.parametrize("exc", [
    httpx.DecodingError(f"bad gzip from {HOST} key={KEY}"),
    httpx.TooManyRedirects(f"redirect loop at {HOST}"),
])
def test_a_request_error_that_is_not_a_transport_error_is_a_named_502(monkeypatch, exc):
    assert not isinstance(exc, httpx.TransportError)     # the case `except httpx.TransportError` would miss
    _post_raising(monkeypatch, exc)
    with pytest.raises(HTTPException) as e:
        real_upstream(MSG, {})
    assert e.value.status_code == 502
    assert e.value.detail == f"upstream unreachable: {type(exc).__name__}"
    _assert_clean(e.value.detail)


def test_the_upstream_key_is_scrubbed_from_a_json_answer(monkeypatch):
    _post_returning(monkeypatch, 200, ('{"echo": "%s", "nested": ["%s"]}' % (KEY, KEY)).encode())
    status, answer = real_upstream(MSG, {})
    assert status == 200 and KEY not in repr(answer)
