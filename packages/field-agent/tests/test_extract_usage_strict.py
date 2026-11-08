"""extract_usage refuses a token count that is not a real non-negative int (S12-4)."""
from types import SimpleNamespace

import pytest

from field_agent.usage import extract_usage

BAD = [True, False, 1.9, 7.0, "12", -1, [3], None]


def _resp(kind, **u):
    usage = {"input_tokens": 5, "output_tokens": 6}
    usage.update(u)
    if kind == "dict":
        return {"model": "m", "usage": usage}
    return SimpleNamespace(model="m", usage=SimpleNamespace(**usage))


@pytest.mark.parametrize("kind", ["dict", "obj"])
@pytest.mark.parametrize("field", ["input_tokens", "output_tokens"])
@pytest.mark.parametrize("bad", BAD)
def test_required_counts_refuse_bad(kind, field, bad):
    with pytest.raises(ValueError) as e:
        extract_usage(_resp(kind, **{field: bad}))
    assert not any(ch.isdigit() for ch in str(e.value))


@pytest.mark.parametrize("kind", ["dict", "obj"])
@pytest.mark.parametrize("bad", [b for b in BAD if b is not None])
def test_cache_count_refuses_bad(kind, bad):
    with pytest.raises(ValueError) as e:
        extract_usage(_resp(kind, cache_read_input_tokens=bad))
    assert not any(ch.isdigit() for ch in str(e.value))


@pytest.mark.parametrize("kind", ["dict", "obj"])
def test_good_values_exact(kind):
    assert extract_usage(_resp(kind)) == {"model": "m", "input_tokens": 5, "output_tokens": 6, "cache_read_tokens": 0}
    assert extract_usage(_resp(kind, cache_read_input_tokens=None))["cache_read_tokens"] == 0
    r = extract_usage(_resp(kind, input_tokens=0, output_tokens=0, cache_read_input_tokens=9))
    assert r == {"model": "m", "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 9}
