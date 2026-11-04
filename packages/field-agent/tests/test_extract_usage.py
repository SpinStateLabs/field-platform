"""FALLBACK pins (tests only): usage.extract_usage, the meter's only reader of an Anthropic response.
A guessed meter is worse than a loud one: missing token counts raise; only the cache field defaults to 0."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from field_agent.usage import extract_usage


def resp(**usage):
    return {"model": "claude-x", "usage": usage}


def test_a_dict_response_maps_the_fields_and_renames_the_cache_key():
    got = extract_usage(resp(input_tokens=10, output_tokens=20, cache_read_input_tokens=5))
    assert got == {"model": "claude-x", "input_tokens": 10, "output_tokens": 20, "cache_read_tokens": 5}


def test_an_sdk_object_response_reads_the_same_way():
    r = SimpleNamespace(model="claude-y", usage=SimpleNamespace(input_tokens=1, output_tokens=2, cache_read_input_tokens=3))
    assert extract_usage(r) == {"model": "claude-y", "input_tokens": 1, "output_tokens": 2, "cache_read_tokens": 3}


@pytest.mark.parametrize("cache", [None, 0])
def test_the_cache_field_alone_defaults_to_zero(cache):
    usage = {"input_tokens": 1, "output_tokens": 1}
    if cache is not None:
        usage["cache_read_input_tokens"] = cache
    assert extract_usage({"model": "m", "usage": usage})["cache_read_tokens"] == 0


def test_a_missing_cache_attribute_on_an_object_is_zero():
    r = SimpleNamespace(model="m", usage=SimpleNamespace(input_tokens=1, output_tokens=2))
    assert extract_usage(r)["cache_read_tokens"] == 0


def test_zero_token_counts_are_real_zeros_not_missing():
    got = extract_usage(resp(input_tokens=0, output_tokens=0))
    assert got["input_tokens"] == 0 and got["output_tokens"] == 0


@pytest.mark.parametrize("response", [{}, {"model": "m"}, {"usage": {"input_tokens": 1, "output_tokens": 1}},
                                      {"model": None, "usage": {}}, {"model": "m", "usage": None},
                                      SimpleNamespace(model="m")], ids=repr)
def test_no_usage_or_no_model_is_a_loud_error(response):
    with pytest.raises(ValueError, match="no usage/model"):
        extract_usage(response)


@pytest.mark.parametrize("usage", [{}, {"input_tokens": 1}, {"output_tokens": 1},
                                   {"input_tokens": None, "output_tokens": 1}], ids=repr)
def test_a_missing_token_count_is_never_guessed_as_zero(usage):
    with pytest.raises(ValueError, match="input_tokens/output_tokens"):
        extract_usage({"model": "m", "usage": usage})


def test_numeric_strings_are_converted_and_garbage_is_a_value_error():
    assert extract_usage(resp(input_tokens="7", output_tokens="8"))["input_tokens"] == 7
    with pytest.raises(ValueError):
        extract_usage(resp(input_tokens="many", output_tokens=1))


def test_the_model_is_stringified():
    assert extract_usage({"model": 5, "usage": {"input_tokens": 1, "output_tokens": 1}})["model"] == "5"
