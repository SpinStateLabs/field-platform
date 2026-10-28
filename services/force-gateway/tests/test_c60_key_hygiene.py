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


@pytest.fixture(autouse=True)
def _fresh_warn_state(monkeypatch):
    monkeypatch.setattr(api, "_warned", set())
    monkeypatch.delenv(api.REQUIRE_TLS_ENV, raising=False)
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


# --- C-112 (reviewer C-104): warn once, opt-in refusal, wider scrub ---------------------------------------


def test_the_http_warning_is_logged_once_per_process_not_per_call(monkeypatch, caplog):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy.example.test:9000")
    _fake_post(monkeypatch, lambda headers: {"ok": True})
    with caplog.at_level(logging.WARNING, logger="force_gateway"):
        for _ in range(3):
            real_upstream(MSG, {})
    assert caplog.text.count("plain http") == 1


def test_require_tls_refuses_an_http_non_private_base_with_a_502_naming_the_variable(monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy.example.test:9000")
    monkeypatch.setenv(api.REQUIRE_TLS_ENV, "1")
    calls = _fake_post(monkeypatch, lambda headers: {"ok": True})
    with pytest.raises(HTTPException) as e:
        real_upstream(MSG, {})
    assert e.value.status_code == 502 and api.REQUIRE_TLS_ENV in e.value.detail
    assert KEY not in e.value.detail
    assert calls == []                                   # nothing was sent


@pytest.mark.parametrize("base", ["https://api.anthropic.com", "https://proxy.example.test:9000",
                                  "http://127.0.0.1:8009", "http://10.0.0.5:8009"])
def test_require_tls_still_allows_https_and_private_http(monkeypatch, base):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", base)
    monkeypatch.setenv(api.REQUIRE_TLS_ENV, "1")
    calls = _fake_post(monkeypatch, lambda headers: {"ok": True})
    assert real_upstream(MSG, {})[0] == 401 and len(calls) == 1


@pytest.mark.parametrize("value", ["", "0", "true", "yes"])
def test_only_the_value_1_turns_require_tls_on(monkeypatch, value):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy.example.test:9000")
    monkeypatch.setenv(api.REQUIRE_TLS_ENV, value)
    calls = _fake_post(monkeypatch, lambda headers: {"ok": True})
    real_upstream(MSG, {})
    assert len(calls) == 1


def test_scrub_also_covers_the_base64_form_and_a_long_prefix_of_the_key():
    import base64

    b64 = base64.b64encode(KEY.encode()).decode()
    body = {"a": f"x{b64}y", "b": [f"leak {KEY[:api.MIN_PREFIX_SCRUB]}..."], "c": KEY}
    out = scrub_secret(body, KEY)
    assert b64 not in repr(out) and KEY[:api.MIN_PREFIX_SCRUB] not in repr(out) and KEY not in repr(out)


def test_a_short_key_is_not_prefix_scrubbed_and_unrelated_text_is_untouched():
    short = "k" * 10
    assert scrub_secret({"t": "kkkkk kkkk"}, short) == {"t": "kkkkk kkkk"}      # no prefix form for a short key
    assert scrub_secret({"t": "hello"}, KEY) == {"t": "hello"}


def test_the_documented_limit_a_key_split_across_list_items_is_not_scrubbed():
    """Not a goal: scrub_secret reduces the echo case, it does not prove the key cannot come back."""
    half = len(KEY) // 2
    body = {"parts": [KEY[:half], KEY[half:]]}
    assert scrub_secret(body, KEY)["parts"][1].startswith(KEY[half:][:3])


def test_the_hygiene_judge_unparseable_output_names_the_class_only(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)

    class Resp:
        status_code = 200

        def json(self):
            raise ValueError("Expecting value near https://user:hunter2@proxy.example.test/x")

    class Client:
        def post(self, *a, **kw):
            return Resp()

    j = AnthropicHygieneJudge(client=Client())
    with pytest.raises(HygieneJudgeError) as e:
        j.judge("text", "preset")
    assert "ValueError" in str(e.value) and "hunter2" not in str(e.value)
