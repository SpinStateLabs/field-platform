"""C-60 (reviewer C-58 finding 3): the sentinel judge's 'unreachable' error names the exception
class only: an httpx transport error's text carries the request URL, and a base URL with
userinfo would leak that secret into a verdict reason."""

from __future__ import annotations

import pytest

from conformance_sentinel.judge import AnthropicJudgeClient, JudgeError

KEY = "sk-ant-DUMMY-C60-KEY-0123456789"


def test_the_judge_error_names_the_class_only(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)

    class Boom:
        def post(self, *a, **kw):
            raise RuntimeError("connect to https://user:hunter2@proxy.example.test failed")

    j = AnthropicJudgeClient(client=Boom())
    with pytest.raises(JudgeError) as e:
        j.judge("do a thing", ["scope one"], "agent-1")
    assert "RuntimeError" in str(e.value)
    assert "hunter2" not in str(e.value) and "user:" not in str(e.value)
