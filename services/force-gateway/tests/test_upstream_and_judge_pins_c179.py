"""C-179 (reviewer C-170 F-C170-2/-3): an upstream non-200 answer is delivered as that status on all
three `/v1/messages` paths (normal, bypass, passthrough) and never as a 200 carrying the error body
or through tool-block enforcement; the hygiene judge refuses to run without a key, does not parse a
non-200 answer as a verdict, and the `anthropic` resolver branch builds the real judge."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from force_gateway.api import create_app
from force_gateway.hygiene_judge import (AnthropicHygieneJudge, HygieneJudgeError, MockHygieneJudge,
                                         resolve_hygiene_judge)

MSG = {"model": "m", "max_tokens": 16, "messages": [{"role": "user", "content": "ping"}]}
SYNTHETIC_KEY = "SYNTHETIC-anthropic-key-not-real"
ERROR_STATUSES = [201, 302, 400, 401, 403, 429, 500, 502, 529]   # any answer but 200, 2xx and 3xx included
# An error body that carries a tool_use block: delivered as a 200 it would be run through
# tool-block enforcement as if it were the model's answer.
ERROR_BODY = {"type": "error", "error": {"type": "api_error", "message": "upstream said no"},
              "content": [{"type": "tool_use", "name": "rm", "input": {}}]}


def upstream_answering(status):
    calls = []

    def upstream(body, headers):
        calls.append(body)
        return status, ERROR_BODY

    upstream.calls = calls
    return upstream


def post(client, **headers):
    return client.post("/v1/messages", json=MSG, headers=headers)


@pytest.mark.parametrize("status", ERROR_STATUSES)
def test_an_upstream_error_is_delivered_with_its_status_on_the_normal_path(status):
    up = upstream_answering(status)
    client = TestClient(create_app(upstream=up))
    r = post(client)
    assert r.status_code == status and r.json()["detail"] == ERROR_BODY
    assert len(up.calls) == 1


@pytest.mark.parametrize("status", ERROR_STATUSES)
def test_an_upstream_error_is_delivered_with_its_status_on_the_bypass_path(status):
    up = upstream_answering(status)
    app = create_app(upstream=up)
    app.state.bypass_remaining = 1
    r = post(TestClient(app))
    assert r.status_code == status and r.json()["detail"] == ERROR_BODY
    assert app.state.bypass_remaining == 0                        # it really was the bypass path
    assert up.calls[0] == MSG                                      # forwarded uninstrumented


@pytest.mark.parametrize("status", ERROR_STATUSES)
def test_an_upstream_error_is_delivered_with_its_status_on_the_passthrough_path(status):
    up = upstream_answering(status)
    client = TestClient(create_app(upstream=up))
    r = post(client, **{"x-force-passthrough": "judge"})
    assert r.status_code == status and r.json()["detail"] == ERROR_BODY


def test_a_healthy_upstream_answer_is_still_a_200_on_every_path():
    def ok(body, headers):
        return 200, {"content": [{"type": "text", "text": "pong"}], "usage": {}}

    for setup, headers in ((lambda a: None, {}), (lambda a: setattr(a.state, "bypass_remaining", 1), {}),
                           (lambda a: None, {"x-force-passthrough": "judge"})):
        app = create_app(upstream=ok)
        setup(app)
        r = post(TestClient(app), **headers)
        assert r.status_code == 200 and r.json()["content"][0]["text"] == "pong"


# --- F-C170-3: the hygiene judge ------------------------------------------------------------


def verdict_body(**over):
    out = {"sycophancy": 0.1, "premise_rigor": 0.9, "overall": 0.8, "rationale": "fine"}
    out.update(over)
    import json
    return {"content": [{"type": "text", "text": json.dumps(out)}], "model": "judge-model",
            "usage": {"input_tokens": 12, "output_tokens": 3}}


class Resp:
    def __init__(self, status, body):
        self.status_code = status
        self._body = body

    def json(self):
        return self._body


class Client:
    def __init__(self, status, body):
        self.status, self.body, self.posts = status, body, []

    def post(self, path, json=None):
        self.posts.append((path, json))
        return Resp(self.status, self.body)


def test_the_anthropic_judge_refuses_to_construct_without_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(HygieneJudgeError, match="ANTHROPIC_API_KEY not set"):
        AnthropicHygieneJudge(client=Client(200, verdict_body()))      # a client does not excuse it
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    with pytest.raises(HygieneJudgeError, match="ANTHROPIC_API_KEY not set"):
        AnthropicHygieneJudge(client=Client(200, verdict_body()))


@pytest.mark.parametrize("status", [201, 400, 401, 429, 500, 503])
def test_a_non_200_judge_answer_is_never_parsed_as_a_verdict(monkeypatch, status):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SYNTHETIC_KEY)
    client = Client(status, verdict_body())                            # a body that WOULD parse
    judge = AnthropicHygieneJudge(client=client)
    with pytest.raises(HygieneJudgeError, match=f"judge upstream returned {status}"):
        judge.judge("some answer", "default")
    assert len(client.posts) == 1


def test_a_200_judge_answer_is_parsed_and_clamped(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SYNTHETIC_KEY)
    judge = AnthropicHygieneJudge(client=Client(200, verdict_body(sycophancy=7, overall=-1)))
    j = judge.judge("some answer", "default")
    assert (j.sycophancy, j.premise_rigor, j.overall) == (1.0, 0.9, 0.0)
    assert (j.model, j.input_tokens, j.output_tokens) == ("judge-model", 12, 3)


# --- the resolver ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["anthropic", "ANTHROPIC", " Anthropic "])
def test_the_resolver_builds_the_real_judge_for_anthropic(monkeypatch, raw):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SYNTHETIC_KEY)
    monkeypatch.setenv("FORCE_HYGIENE_JUDGE", raw)
    assert isinstance(resolve_hygiene_judge(), AnthropicHygieneJudge)


def test_the_resolver_without_a_key_does_not_fall_back_silently(monkeypatch):
    monkeypatch.setenv("FORCE_HYGIENE_JUDGE", "anthropic")
    with pytest.raises(HygieneJudgeError, match="ANTHROPIC_API_KEY not set"):
        resolve_hygiene_judge()


@pytest.mark.parametrize(("raw", "kind"), [
    ("mock", MockHygieneJudge), ("MOCK", MockHygieneJudge), ("", None), ("off", None),
    ("anthropic2", None), ("anthropik", None), ("true", None)])
def test_the_resolver_other_values(monkeypatch, raw, kind):
    monkeypatch.setenv("FORCE_HYGIENE_JUDGE", raw)
    got = resolve_hygiene_judge()
    assert got is None if kind is None else isinstance(got, kind)
