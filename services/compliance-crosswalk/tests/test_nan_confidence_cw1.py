"""F-CW-1 (reviewer C-1082, Lane 14): a non-finite confidence never clears the precision floor.

``max(0.0, min(1.0, float(nan)))`` is 1.0 (``min(1.0, nan)`` returns its first argument), and ``nan < floor`` is False,
so a NaN confidence from a suggester became a CANDIDATE at full confidence. A confidence that is not a finite number is
now the conservative default (``unmapped — review required``), through ``suggest`` for any suggester and inside the
Anthropic suggester's own parse."""

from __future__ import annotations

import json
import math

import pytest

from compliance_crosswalk.suggestions import AnthropicSuggester, suggest

MANIFEST = {"agent": {"description": "chases overdue invoices"}}
REVIEW = "unmapped — review required"


class _Stub:
    name = "stub"

    def __init__(self, confidence):
        self.confidence = confidence

    def suggest_one(self, path, value):
        return ("nist-ai-rmf", "System purpose is documented.", self.confidence, "a vetted framework")


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), float("-inf"), "nan", "inf", "-inf"],
                         ids=repr)
def test_a_non_finite_confidence_is_review_required_never_a_candidate(confidence):
    (s,) = suggest(MANIFEST, _Stub(confidence), floor=0.8)
    assert s.status == REVIEW
    assert s.framework is None and s.candidate_statement is None
    assert s.confidence == 0.0 and math.isfinite(s.confidence)
    assert "suggester error" in s.rationale


@pytest.mark.parametrize("confidence, status", [(0.8, "candidate"), (1.0, "candidate"), (0.79, REVIEW), (0.0, REVIEW)])
def test_a_finite_confidence_still_follows_the_floor(confidence, status):
    (s,) = suggest(MANIFEST, _Stub(confidence), floor=0.8)
    assert s.status == status


class _Resp:
    status_code = 200

    def __init__(self, text):
        self._text = text

    def json(self):
        return {"content": [{"type": "text", "text": self._text}]}


class _Client:
    def __init__(self, text):
        self._text = text

    def post(self, url, json=None, **kwargs):
        return _Resp(self._text)


def _suggester(monkeypatch, confidence_literal):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-test-key-not-a-secret")
    text = ('{"framework": "nist-ai-rmf", "statement": "s", "confidence": %s, "rationale": "r"}' % confidence_literal)
    return AnthropicSuggester(model="test-model", client=_Client(text))


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_the_anthropic_suggester_refuses_a_non_finite_confidence(monkeypatch, literal):
    with pytest.raises(ValueError, match="finite"):
        _suggester(monkeypatch, literal).suggest_one("agent.description", "x")


@pytest.mark.parametrize("literal, expected", [("0.9", 0.9), ("7", 1.0), ("-3", 0.0), ("1e999", None)])
def test_the_anthropic_suggester_still_clamps_a_finite_confidence(monkeypatch, literal, expected):
    s = _suggester(monkeypatch, literal)
    if expected is None:                      # 1e999 overflows to inf in the JSON parser: a non-finite value
        with pytest.raises(ValueError, match="finite"):
            s.suggest_one("agent.description", "x")
    else:
        assert s.suggest_one("agent.description", "x")[2] == expected


def test_the_json_the_suggester_parses_really_accepts_the_literals():
    assert math.isnan(json.loads('{"c": NaN}')["c"]) and math.isinf(json.loads('{"c": Infinity}')["c"])
