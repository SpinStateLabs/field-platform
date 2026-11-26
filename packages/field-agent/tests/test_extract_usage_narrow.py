"""S12-4 (rebuild of PR 1019, narrow rule): extract_usage refuses only what would meter WRONG (a bool, a non-integral number, a
negative, anything int() cannot read) and keeps accepting a lossless coercion ("7", 3.0). The two pins on main
(test_extract_usage.py, test_usage_extract.py) are unchanged."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from field_agent.usage import extract_usage

REFUSED = [1.9, True, False, -1, -0.5, float("nan"), float("inf"), "abc", "1.5", "-1", "", [3], {}, Decimal("1.9")]
ACCEPTED = [("7", 7), ("12", 12), (3.0, 3), (7.0, 7), (0, 0), (5, 5), (Decimal("4"), 4)]
FIELDS = [("input_tokens", "input_tokens"), ("output_tokens", "output_tokens"),
          ("cache_read_input_tokens", "cache_read_tokens")]


def _resp(kind, **u):
    usage = {"input_tokens": 5, "output_tokens": 6}
    usage.update(u)
    if kind == "dict":
        return {"model": "m", "usage": usage}
    return SimpleNamespace(model="m", usage=SimpleNamespace(**usage))


@pytest.mark.parametrize("kind", ["dict", "obj"])
@pytest.mark.parametrize("field,_out", FIELDS)
@pytest.mark.parametrize("bad", REFUSED, ids=lambda v: repr(v))
def test_a_count_that_would_meter_wrong_is_refused_naming_the_type_not_the_value(kind, field, _out, bad):
    with pytest.raises(ValueError) as e:
        extract_usage(_resp(kind, **{field: bad}))
    msg = str(e.value)
    assert field in msg and "must be a non-negative whole number" in msg
    assert not any(ch.isdigit() for ch in msg.replace(field, ""))


@pytest.mark.parametrize("kind", ["dict", "obj"])
@pytest.mark.parametrize("field,out", FIELDS)
@pytest.mark.parametrize("good,want", ACCEPTED, ids=lambda v: repr(v))
def test_a_lossless_count_is_accepted_as_an_exact_int(kind, field, out, good, want):
    got = extract_usage(_resp(kind, **{field: good}))
    assert got[out] == want and type(got[out]) is int


@pytest.mark.parametrize("kind", ["dict", "obj"])
def test_the_cache_field_may_be_absent_or_null_and_is_then_zero(kind):
    assert extract_usage(_resp(kind))["cache_read_tokens"] == 0
    assert extract_usage(_resp(kind, cache_read_input_tokens=None))["cache_read_tokens"] == 0


def test_the_missing_required_counts_are_still_a_value_error():
    with pytest.raises(ValueError):
        extract_usage({"model": "m", "usage": {"input_tokens": 1}})
    with pytest.raises(ValueError):
        extract_usage({"model": "m", "usage": {"input_tokens": None, "output_tokens": 1}})
