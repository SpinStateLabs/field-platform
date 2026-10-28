"""C-60 (reviewer C-58, probed with a dummy key): the gateway must not hand the upstream API key
back to the caller if an upstream echoes the request headers, must say so when the key goes over
plain http to a non-private host, and the hygiene judge's error text must not carry URL userinfo."""

from __future__ import annotations

import logging

import pytest

from force_gateway import api
from force_gateway.api import _base_url_warning, real_upstream, scrub_secret
from force_gateway.hygiene_judge import AnthropicHygieneJudge, HygieneJudgeError

KEY = "sk-ant-DUMMY-C60-KEY-0123456789"
MSG = {"model": "m", "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}


def test_scrub_replaces_the_secret_in_strings_nested_values_and_keys():
    body = {"error": {"message": f"bad key {KEY}", "headers": {"x-api-key": KEY, KEY: "v"}},
            "content": [{"type": "text", "text": f"a{KEY}b"}, 7, None, [KEY]], "n": 3}
    out = scrub_secret(body, KEY)
    assert KEY not in repr(out)
    assert out["n"] == 3 and out["content"][1] == 7 and out["content"][2] is None
    assert out["error"]["headers"]["x-api-key"] == api.REDACTED


def test_scrub_leaves_a_body_without_the_secret_unchanged_and_ignores_an_empty_secret():
    body = {"id": "msg_1", "content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 3}}
    assert scrub_secret(body, KEY) == body
    assert scrub_secret(body, "") is body


def _fake_post(monkeypatch, reply):
    import httpx
    calls = []

    class Resp:
        status_code = 401

        def json(self):
            return reply(calls[-1][1])

    def fake_post(url, json=None, headers=None, timeout=None):
        calls.append((url, headers))
        return Resp()

    monkeypatch.setattr(httpx, "post", fake_post)
    return calls


def test_an_upstream_that_echoes_the_request_headers_does_not_return_the_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    _fake_post(monkeypatch, lambda headers: {"error": {"echo": dict(headers)}})
    status, body = real_upstream(MSG, {})
    assert status == 401
    assert KEY not in repr(body)
    assert body["error"]["echo"]["x-api-key"] == api.REDACTED


@pytest.mark.parametrize("base,warns", [
    ("https://api.anthropic.com", False),
    ("https://proxy.example.test:9000", False),
    ("http://127.0.0.1:8009", False),
    ("http://localhost:8009", False),
    ("http://10.0.0.5:8009", False),
    ("http://proxy.example.test:9000", True),
    ("http://8.8.8.8:9000", True),
])
def test_base_url_warning(base, warns):
    assert (_base_url_warning(base) is not None) is warns


def test_the_warning_never_carries_the_key_or_url_userinfo(monkeypatch, caplog):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://user:hunter2@proxy.example.test:9000")
    _fake_post(monkeypatch, lambda headers: {"ok": True})
    with caplog.at_level(logging.WARNING, logger="force_gateway"):
        real_upstream(MSG, {})
    text = caplog.text
    assert "plain http" in text and "proxy.example.test" in text
    assert KEY not in text and "hunter2" not in text and "user:" not in text


def test_the_hygiene_judge_error_names_the_class_only_not_the_url_userinfo(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)

    class Boom:
        def post(self, *a, **kw):
            raise RuntimeError("connect to https://user:hunter2@proxy.example.test failed")

    j = AnthropicHygieneJudge(client=Boom())
    with pytest.raises(HygieneJudgeError) as e:
        j.judge("text", "preset")
    assert "RuntimeError" in str(e.value)
    assert "hunter2" not in str(e.value) and "user:" not in str(e.value)
