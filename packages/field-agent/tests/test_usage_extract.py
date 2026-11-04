"""`extract_usage` and `FieldAgent.report_usage_from`: pinned (scout P-12, test gap, tests only).

`extract_usage` turns an Anthropic Messages response (a dict or an SDK object, no `anthropic` import) into the meter's
fields. Its contract: `cache_read_input_tokens` maps to `cache_read_tokens` and defaults to 0; a missing usage, model or
token count raises ValueError rather than guessing a zero ("a guessed meter is worse than a loud one")."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from field_agent.usage import extract_usage
from tests.conftest import AGENT_ID  # noqa: F401  (the stack fixture comes from conftest)


def _resp(**usage_over):
    usage = {"input_tokens": 1_000, "output_tokens": 200, "cache_read_input_tokens": 50}
    usage.update(usage_over)
    return {"model": "claude-haiku-4-5", "usage": usage}


def test_a_dict_response_maps_the_cache_field():
    assert extract_usage(_resp()) == {
        "model": "claude-haiku-4-5", "input_tokens": 1_000, "output_tokens": 200, "cache_read_tokens": 50,
    }


def test_an_sdk_style_object_gives_the_same_fields():
    obj = SimpleNamespace(model="claude-haiku-4-5", usage=SimpleNamespace(
        input_tokens=1_000, output_tokens=200, cache_read_input_tokens=50))
    assert extract_usage(obj) == extract_usage(_resp())


def test_a_dict_usage_inside_an_object_and_an_object_usage_inside_a_dict_both_work():
    assert extract_usage(SimpleNamespace(model="m", usage={"input_tokens": 1, "output_tokens": 2}))["input_tokens"] == 1
    assert extract_usage({"model": "m", "usage": SimpleNamespace(input_tokens=1, output_tokens=2)})["output_tokens"] == 2


@pytest.mark.parametrize("usage", [
    {"input_tokens": 1, "output_tokens": 2},                                  # absent
    {"input_tokens": 1, "output_tokens": 2, "cache_read_input_tokens": None},  # None
    {"input_tokens": 1, "output_tokens": 2, "cache_read_input_tokens": 0},
])
def test_cache_read_defaults_to_zero(usage):
    assert extract_usage({"model": "m", "usage": usage})["cache_read_tokens"] == 0


@pytest.mark.parametrize("response", [
    {"model": "m"},                                   # no usage
    {"usage": {"input_tokens": 1, "output_tokens": 2}},  # no model
    {"model": None, "usage": {"input_tokens": 1, "output_tokens": 2}},
    {"model": "m", "usage": None},
    {},
    SimpleNamespace(),
])
def test_a_missing_usage_or_model_is_a_value_error(response):
    with pytest.raises(ValueError, match="no usage/model"):
        extract_usage(response)


@pytest.mark.parametrize("usage", [
    {"output_tokens": 2},
    {"input_tokens": 1},
    {"input_tokens": None, "output_tokens": 2},
    {"input_tokens": 1, "output_tokens": None},
    {},
])
def test_a_missing_token_count_is_a_value_error_not_a_guessed_zero(usage):
    with pytest.raises(ValueError, match="input_tokens/output_tokens"):
        extract_usage({"model": "m", "usage": usage})


def test_a_zero_token_count_is_a_real_zero_not_missing():
    out = extract_usage({"model": "m", "usage": {"input_tokens": 0, "output_tokens": 0}})
    assert (out["input_tokens"], out["output_tokens"]) == (0, 0)


def test_counts_are_coerced_to_int_and_the_model_to_str():
    out = extract_usage({"model": 5, "usage": {"input_tokens": "12", "output_tokens": 3.0, "cache_read_input_tokens": "7"}})
    assert out == {"model": "5", "input_tokens": 12, "output_tokens": 3, "cache_read_tokens": 7}
    assert all(type(out[k]) is int for k in ("input_tokens", "output_tokens", "cache_read_tokens"))


def test_report_usage_from_forwards_the_extracted_fields_and_the_note(stack):
    stack.set_cap()
    agent = stack.make_agent()
    calls = []
    real = agent.report_usage

    def spy(*args, **kw):
        calls.append((args, kw))
        return real(*args, **kw)

    agent.report_usage = spy
    report = agent.report_usage_from(_resp(), note="from a messages response")
    assert calls == [((), {
        "model": "claude-haiku-4-5", "input_tokens": 1_000, "output_tokens": 200, "cache_read_tokens": 50,
        "note": "from a messages response",
    })]
    assert report.record.model == "claude-haiku-4-5"


def test_report_usage_from_refuses_a_response_with_no_usage_and_reports_nothing(stack):
    stack.set_cap()
    agent = stack.make_agent()
    before = len(stack.events("usage.recorded"))
    with pytest.raises(ValueError):
        agent.report_usage_from({"model": "claude-haiku-4-5"})
    assert len(stack.events("usage.recorded")) == before
