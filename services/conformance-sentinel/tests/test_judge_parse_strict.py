"""`AnthropicJudgeClient.judge` parses the verdict strictly; `resolve_floor` ignores a non-finite floor (scout P-20).

Before: `confidence` was `max(0.0, min(1.0, float(x)))`, and `float("nan")` clamps to 1.0, so a NaN confidence cleared any
floor in the engine's `jv.conforming is True and jv.confidence >= floor` check; `conforming` went through `bool()`, so the
string "false" became True. `json.loads` accepts the bare tokens NaN and Infinity. Both now raise JudgeError (the engine
escalates on JudgeError). `FIELD_JUDGE_CONFIDENCE_FLOOR=-inf` clamped to 0.0, a floor every confidence clears: now the default."""

from __future__ import annotations

import json

import pytest

from conformance_sentinel.judge import AnthropicJudgeClient, JudgeError, resolve_floor

KEY = "sk-ant-synthetic-test-key-0000"


class _Resp:
    status_code = 200

    def __init__(self, text: str):
        self._body = {"content": [{"type": "text", "text": text}], "model": "m", "usage": {"input_tokens": 1, "output_tokens": 1}}

    def json(self):
        return self._body


class _Client:
    def __init__(self, text: str):
        self.text = text

    def post(self, *a, **kw):
        return _Resp(self.text)


def _judge(monkeypatch, **over):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    body = json.dumps({"conforming": True, "confidence": 0.9, "cited_scope": "draft invoices", "rationale": "r", **over})
    return AnthropicJudgeClient(client=_Client(body)).judge("draft invoices", ["draft invoices"], "invoicing-agent")


def test_a_well_formed_verdict_is_returned(monkeypatch):
    v = _judge(monkeypatch)
    assert (v.conforming, v.confidence) == (True, 0.9)
    assert _judge(monkeypatch, conforming=False).conforming is False
    assert _judge(monkeypatch, conforming=None).conforming is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_confidence_is_a_judge_error(monkeypatch, value):
    with pytest.raises(JudgeError):
        _judge(monkeypatch, confidence=value)


@pytest.mark.parametrize("value", [True, False, "0.9", None, [0.9]])
def test_a_non_number_confidence_is_a_judge_error(monkeypatch, value):
    with pytest.raises(JudgeError):
        _judge(monkeypatch, confidence=value)


def test_a_finite_out_of_range_confidence_is_still_clamped(monkeypatch):
    assert _judge(monkeypatch, confidence=7).confidence == 1.0
    assert _judge(monkeypatch, confidence=-2).confidence == 0.0
    assert _judge(monkeypatch, confidence=1).confidence == 1.0


@pytest.mark.parametrize("value", ["false", "true", "yes", 0, 1, [], {}, "null"])
def test_conforming_other_than_true_false_null_is_a_judge_error(monkeypatch, value):
    with pytest.raises(JudgeError):
        _judge(monkeypatch, conforming=value)


def test_the_error_text_names_the_class_only(monkeypatch):
    with pytest.raises(JudgeError) as e:
        _judge(monkeypatch, confidence=float("nan"))
    assert str(e.value).startswith("judge returned unparseable verdict: ")
    assert "nan" not in str(e.value).lower().replace("unparseable", "")


@pytest.mark.parametrize("raw,expected", [
    ("nan", 0.8), ("inf", 0.8), ("-inf", 0.8), ("NaN", 0.8), ("", 0.8), ("abc", 0.8),   # non-finite or unparseable: the default
    ("0.5", 0.5), ("0", 0.0), ("1", 1.0), ("7", 1.0), ("-3", 0.0),                       # finite: parsed and clamped as before
])
def test_resolve_floor(monkeypatch, raw, expected):
    monkeypatch.setenv("FIELD_JUDGE_CONFIDENCE_FLOOR", raw)
    assert resolve_floor() == expected
