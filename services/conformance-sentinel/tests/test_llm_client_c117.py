"""C-117 (reviewer C-187): the semantic judge builds its client through the shared, checked helper."""

import pytest

from conformance_sentinel.judge import AnthropicJudgeClient, JudgeError


def test_a_plain_http_gateway_outside_the_estate_is_refused_not_used(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-real-key")
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://gw.example.test:8009")
    with pytest.raises(JudgeError) as e:
        AnthropicJudgeClient()
    assert "gw.example.test" in str(e.value) and "sk-ant-test" not in str(e.value)


def test_an_internal_gateway_still_builds(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-a-real-key")
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009")
    assert AnthropicJudgeClient()._client.base_url.host == "forcegw"
