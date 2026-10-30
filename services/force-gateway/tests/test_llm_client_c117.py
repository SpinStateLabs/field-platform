"""C-117 (reviewer C-187): the hygiene judge builds its client through the shared, checked helper."""

import pytest

from force_gateway.hygiene_judge import AnthropicHygieneJudge, HygieneJudgeError


def test_a_plain_http_gateway_outside_the_estate_is_refused_not_used(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-real-key")
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://gw.example.test:8009")
    with pytest.raises(HygieneJudgeError) as e:
        AnthropicHygieneJudge()
    assert "gw.example.test" in str(e.value) and "sk-ant-test" not in str(e.value)


def test_an_internal_gateway_and_the_default_host_still_build(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-real-key")
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009")
    assert AnthropicHygieneJudge()._client.base_url.host == "forcegw"
    monkeypatch.delenv("FORCE_GATEWAY_URL")
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    assert AnthropicHygieneJudge()._client.base_url.host == "api.anthropic.com"
