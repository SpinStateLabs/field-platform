"""A ledger payload with NaN or Infinity cannot be re-verified (scout S-A3): the hash
is taken over a `NaN` token, the served JSON carries `null`, and the chain then reads
as tampered. Seal time must refuse it."""
from __future__ import annotations

import json

import pytest

from field_core.ledger import compute_event_hash, make_event, reject_non_finite


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("shape", [
    lambda v: {"v": v},
    lambda v: {"a": {"b": [1, {"c": v}]}},
    lambda v: {"a": [v]},
])
def test_make_event_refuses_a_non_finite_number_anywhere_in_the_payload(bad, shape):
    with pytest.raises(ValueError, match="non-finite"):
        make_event("x", shape(bad))


@pytest.mark.parametrize("ok", [0, 1, -1, 2**70, 1.5, -0.0, 1e308, True, None, "nan", "inf"])
def test_finite_numbers_and_strings_that_look_like_them_are_fine(ok):
    e = make_event("x", {"v": ok})
    assert compute_event_hash(json.loads(e.model_dump_json())) == e.hash


def test_a_sealed_event_reverifies_from_its_served_json():
    e = make_event("x", {"v": 1.25, "w": [1, 2, {"k": "v"}]})
    assert compute_event_hash(json.loads(e.model_dump_json())) == e.hash


def test_the_message_never_carries_the_value_or_a_key():
    with pytest.raises(ValueError) as exc:
        reject_non_finite({"secret-key-name": float("nan")})
    assert "secret-key-name" not in str(exc.value) and "nan" not in str(exc.value).lower().replace("non-finite", "")


def test_a_deeply_nested_payload_does_not_hit_the_recursion_limit():
    deep: object = 1.0
    for _ in range(5000):
        deep = [deep]
    reject_non_finite({"v": deep})            # finite: must simply return
