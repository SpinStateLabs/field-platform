"""v1.2 D2e — the three platform LLM callers route by field_core.llm.

sentinel `AnthropicJudgeClient`, crosswalk `AnthropicSuggester` and the
gateway's own `AnthropicHygieneJudge` each build their httpx client from
`anthropic_base_url()` + `anthropic_headers(key)`. Proven here per caller:
base-URL precedence (FORCE_GATEWAY_URL > ANTHROPIC_BASE_URL > default), the
platform headers only toward FORCE_GATEWAY_URL, and a real call through an
in-process secret-protected gateway answering 200 (not 401), forwarded as
passthrough. The sibling services are imported only if installed (CI and
the dev venv install every service)."""

import json

import pytest
from fastapi.testclient import TestClient

from force_gateway.api import create_app, mock_upstream
from force_gateway.hygiene_judge import RUBRIC as HYGIENE_RUBRIC, AnthropicHygieneJudge

from test_d2_upstream_passthrough import route_httpx_clients_to

sentinel_judge = pytest.importorskip("conformance_sentinel.judge")
crosswalk_suggestions = pytest.importorskip("compliance_crosswalk.suggestions")

SECRET = "synthetic-shared-secret-for-tests"
SYNTHETIC_KEY = "SYNTHETIC-anthropic-key-not-real"

CALLERS = {
    "sentinel-judge": lambda: sentinel_judge.AnthropicJudgeClient(),
    "crosswalk-suggester": lambda: crosswalk_suggestions.AnthropicSuggester(),
    "gateway-hygiene-judge": lambda: AnthropicHygieneJudge(),
}


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", SYNTHETIC_KEY)


def built(monkeypatch, name):
    """Construct the caller for real and report the base_url/headers it chose."""
    import httpx

    seen = {}

    def factory(base_url="", timeout=None, headers=None, **kw):
        seen.update(base_url=str(base_url), headers=dict(headers or {}))
        return object()

    monkeypatch.setattr(httpx, "Client", factory)
    CALLERS[name]()
    return seen


@pytest.mark.parametrize("name", sorted(CALLERS))
def test_default_host_when_nothing_is_set(monkeypatch, name):
    seen = built(monkeypatch, name)
    assert seen["base_url"] == "https://api.anthropic.com"
    assert seen["headers"] == {"x-api-key": SYNTHETIC_KEY, "anthropic-version": "2023-06-01"}


@pytest.mark.parametrize("name", sorted(CALLERS))
def test_anthropic_base_url_used_when_no_gateway(monkeypatch, name):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy.example.test:9000")
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    seen = built(monkeypatch, name)
    assert seen["base_url"] == "http://proxy.example.test:9000"
    assert "x-field-auth" not in seen["headers"]  # never to a possible third party
    assert "x-force-passthrough" not in seen["headers"]


@pytest.mark.parametrize("name", sorted(CALLERS))
def test_force_gateway_url_wins_and_carries_platform_headers(monkeypatch, name):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy.example.test:9000")
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009/")
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    seen = built(monkeypatch, name)
    assert seen["base_url"] == "http://forcegw:8009"
    assert seen["headers"]["x-force-passthrough"] == "judge"
    assert seen["headers"]["x-field-auth"] == SECRET
    assert seen["headers"]["x-api-key"] == SYNTHETIC_KEY


def _answer(body):
    system = body.get("system")
    if system == sentinel_judge._RUBRIC:
        payload = {"conforming": True, "confidence": 0.93, "cited_scope": "draft invoices",
                   "rationale": "synthetic verdict"}
    elif system == crosswalk_suggestions._RUBRIC:
        payload = {"framework": None, "statement": None, "confidence": 0.1,
                   "rationale": "synthetic decline"}
    elif system == HYGIENE_RUBRIC:
        payload = {"sycophancy": 0.8, "premise_rigor": 0.8, "overall": 0.8,
                   "rationale": "synthetic judgment"}
    else:
        return None
    return {"model": "synthetic-upstream", "type": "message",
            "content": [{"type": "text", "text": json.dumps(payload)}],
            "usage": {"input_tokens": 5, "output_tokens": 5}}


def test_every_caller_gets_200_through_a_secret_gateway_as_passthrough(monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", SECRET)
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009")
    forwarded = []

    def upstream(body, headers):
        forwarded.append(body)
        answer = _answer(body)
        return (200, answer) if answer is not None else mock_upstream(body, headers)

    app = create_app(upstream=upstream, sample_every=0)
    route_httpx_clients_to(monkeypatch, app)

    verdict = CALLERS["sentinel-judge"]().judge("draft invoices", ["draft invoices"], "agent-x")
    assert (verdict.conforming, verdict.confidence) == (True, 0.93)
    framework, statement, confidence, _ = CALLERS["crosswalk-suggester"]().suggest_one(
        "identity.principal", "Founder")
    assert (framework, statement, confidence) == (None, None, 0.1)
    judgment = CALLERS["gateway-hygiene-judge"]().judge("some response", "analysis")
    assert judgment.overall == 0.8

    # every call was forwarded untouched (its own rubric as the system prompt)
    assert [b["system"] for b in forwarded] == [
        sentinel_judge._RUBRIC, crosswalk_suggestions._RUBRIC, HYGIENE_RUBRIC]
    t = TestClient(app, headers={"x-field-auth": SECRET}).get("/telemetry").json()
    assert t["coverage"]["passthrough"] == 3
    assert t["total_requests"] == 0 and t["by_preset"] == {}
