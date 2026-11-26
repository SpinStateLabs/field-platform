"""`AnthropicHygieneJudge.judge`: scores are finite JSON numbers, clamped to [0, 1]; anything else is an error (scout P-21).

Before: `max(0.0, min(1.0, float(x)))`. `float("nan")` clamps to 1.0 (`min(1.0, nan)` is 1.0), so a NaN `premise_rigor`
read as perfect rigor and a NaN `sycophancy` as maximum sycophancy; `true` became 1.0 and the string "0.5" 0.5. Python's
`json.loads` accepts the bare tokens NaN and Infinity, so a model reply can carry them. The error names the class only."""

from __future__ import annotations

import json

import pytest

from force_gateway.hygiene_judge import AnthropicHygieneJudge, HygieneJudgeError

KEY = "sk-ant-synthetic-test-key-0000"
FIELDS = ("sycophancy", "premise_rigor", "overall")


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


def _judge(monkeypatch, scores: dict):
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    # json.dumps writes NaN / Infinity as the bare tokens json.loads accepts: what a model reply can carry
    body = json.dumps({"sycophancy": 0.2, "premise_rigor": 0.8, "overall": 0.7, "rationale": "r", **scores})
    return AnthropicHygieneJudge(client=_Client(body)).judge("text", "preset")


def test_a_well_formed_reply_is_returned_as_is(monkeypatch):
    j = _judge(monkeypatch, {})
    assert (j.sycophancy, j.premise_rigor, j.overall) == (0.2, 0.8, 0.7)


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_score_is_an_error_not_a_clamped_one(monkeypatch, field, value):
    with pytest.raises(HygieneJudgeError):
        _judge(monkeypatch, {field: value})


@pytest.mark.parametrize("field", FIELDS)
@pytest.mark.parametrize("value", [True, False, "0.5", None, [0.5], {"v": 0.5}])
def test_a_non_number_score_is_an_error(monkeypatch, field, value):
    with pytest.raises(HygieneJudgeError):
        _judge(monkeypatch, {field: value})


@pytest.mark.parametrize("field", FIELDS)
def test_an_out_of_range_finite_score_is_still_clamped(monkeypatch, field):
    assert getattr(_judge(monkeypatch, {field: 7}), field) == 1.0
    assert getattr(_judge(monkeypatch, {field: -3.5}), field) == 0.0
    assert getattr(_judge(monkeypatch, {field: 1e308}), field) == 1.0


def test_an_integer_zero_and_one_are_numbers(monkeypatch):
    j = _judge(monkeypatch, {"sycophancy": 0, "premise_rigor": 1})
    assert (j.sycophancy, j.premise_rigor) == (0.0, 1.0)


def test_the_error_text_names_the_class_only(monkeypatch):
    with pytest.raises(HygieneJudgeError) as e:
        _judge(monkeypatch, {"premise_rigor": float("nan")})
    assert str(e.value).startswith("unparseable judge output: ")
    assert "nan" not in str(e.value).lower().replace("unparseable", "")
