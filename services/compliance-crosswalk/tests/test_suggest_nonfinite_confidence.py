"""S5-19: the precision floor is the suggester's safety gate and NaN walked through it twice. A non-finite or boolean
confidence is a ``review required`` entry, never a candidate; the floor setting cannot be NaN, infinite or negative
(a floor of 0 admits every proposal); a model reply of ``{"confidence": NaN}`` is refused, not clamped to 1.0."""

from __future__ import annotations

import json
import math

import pytest

from compliance_crosswalk.suggestions import (
    AnthropicSuggester, MockSuggester, resolve_suggest_floor, suggest,
)

MANIFEST = {"zzz": {"q": 1}}
REVIEW = "unmapped — review required"


def run(confidence, floor=0.8):
    s = MockSuggester(rules={"zzz.q": ("nist-ai-rmf", "a statement", confidence, "r")})
    return suggest(MANIFEST, s, floor)[0]


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), True, False, "x", "nan", "inf", None, [1]],
                         ids=repr)
def test_a_bad_confidence_is_review_required_never_a_candidate(bad):
    out = run(bad)
    assert out.status == REVIEW and out.framework is None and out.candidate_statement is None
    assert out.confidence == 0.0 and math.isfinite(out.confidence)
    assert "suggester error" in out.rationale


@pytest.mark.parametrize("ok,status", [(0.9, "candidate"), (0.8, "candidate"), (0.79, REVIEW), (0, REVIEW),
                                       ("0.95", "candidate"), (1, "candidate")])
def test_finite_confidences_behave_as_before(ok, status):
    assert run(ok).status == status


def test_a_nan_floor_admits_nothing():
    assert run(0.99, floor=float("nan")).status == REVIEW


@pytest.mark.parametrize("raw,expect", [("nan", 0.8), ("NaN", 0.8), ("inf", 0.8), ("-inf", 0.8), ("-1", 0.8),
                                        ("-0.0001", 0.8), ("", 0.8), ("x", 0.8), ("0.8", 0.8), ("0.6", 0.6),
                                        ("0", 0.0), ("1", 1.0), ("2.5", 1.0)])
def test_the_floor_setting(monkeypatch, raw, expect):
    monkeypatch.setenv("CROSSWALK_SUGGEST_FLOOR", raw)
    assert resolve_suggest_floor() == expect


def test_a_custom_default_is_what_a_bad_value_falls_back_to(monkeypatch):
    monkeypatch.setenv("CROSSWALK_SUGGEST_FLOOR", "nan")
    assert resolve_suggest_floor(default=0.9) == 0.9


# ---- the model's reply ------------------------------------------------------------------------------------------------

class Resp:
    status_code = 200

    def __init__(self, text):
        self._text = text

    def json(self):
        return {"content": [{"type": "text", "text": self._text}]}


class Client:
    def __init__(self, text):
        self.text = text

    def post(self, *a, **k):
        return Resp(self.text)


@pytest.fixture()
def suggester(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    def make(confidence_json):
        body = ('{"framework": "nist-ai-rmf", "statement": "s", "confidence": %s, "rationale": "r"}'
                % confidence_json)
        return AnthropicSuggester(client=Client(body))
    return make


@pytest.mark.parametrize("raw", ["NaN", "Infinity", "-Infinity", "true", '"x"', "null", "[1]"])
def test_a_non_finite_or_non_numeric_model_confidence_is_refused(suggester, raw):
    with pytest.raises((ValueError, TypeError)):
        suggester(raw).suggest_one("zzz.q", 1)
    out = suggest(MANIFEST, suggester(raw), 0.8)[0]
    assert out.status == REVIEW and out.confidence == 0.0


@pytest.mark.parametrize("raw,expect", [("0.9", 0.9), ("1.7", 1.0), ("-0.5", 0.0), ("0", 0.0), ("1", 1.0)])
def test_a_finite_model_confidence_is_still_clamped_to_zero_one(suggester, raw, expect):
    assert suggester(raw).suggest_one("zzz.q", 1)[2] == expect


def test_the_literal_json_nan_is_what_the_old_clamp_turned_into_one():
    """the reason for the guard: json accepts NaN, and min(1.0, nan) is 1.0"""
    nan = json.loads('{"c": NaN}')["c"]
    assert math.isnan(nan) and max(0.0, min(1.0, nan)) == 1.0
