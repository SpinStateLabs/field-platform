"""S9-7: `_strip_reserved` handles tuples the way `_has_reserved` does.

`_has_reserved` looks inside lists AND tuples; `_strip_reserved` rebuilt dicts and lists but returned a tuple as it was, so a payload
like `{"items": ({"operator_claimed": "mallory"},)}` was reported as holding a reserved key and then stored with it intact by
`merge_payload`, `strip_reserved_unless_asserted` and `admit_ledger_event`. In-process callers only (HTTP JSON has no tuples), but
every service append goes through `merge_payload`. Decision pinned: a tuple stays a tuple, with its items cleaned. Armed mode is
switched on with FIELD_OPERATOR_REQUIRE, as test_operator_auth.py does."""

import pytest

from field_core import operator_auth as oa

RES = "operator_claimed"
assert oa._is_reserved(RES)


@pytest.fixture()
def armed(monkeypatch, tmp_path):
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    monkeypatch.delenv(oa.ENV_REGISTRY, raising=False)


CASES = {
    "tuple-of-dicts": ({"items": ({RES: "mallory", "ok": 1},)}, {"items": ({"ok": 1},)}),
    "list-in-tuple": ({"x": ([{RES: "m"}],)}, {"x": ([{}],)}),
    "tuple-in-dict-in-tuple": ({"a": ({"b": ({RES: "m", "keep": 2},)},)}, {"a": ({"b": ({"keep": 2},)},)}),
    "tuple-in-list": ({"l": [({RES: "m"},)]}, {"l": [({},)]}),
    "top-level-key": ({RES: "m", "n": 1}, {"n": 1}),
}


@pytest.mark.parametrize("name", list(CASES))
def test_a_reserved_key_nested_in_a_tuple_is_stripped_and_the_tuple_stays_a_tuple(name):
    before, after = CASES[name]
    out = oa._strip_reserved(before)
    assert out == after
    assert isinstance(out, dict)


def test_a_tuple_stays_a_tuple_and_a_list_stays_a_list():
    out = oa._strip_reserved({"t": ({RES: "m"}, 1), "l": [{RES: "m"}, 1]})
    assert isinstance(out["t"], tuple) and isinstance(out["l"], list)
    assert out == {"t": ({}, 1), "l": [{}, 1]}


def test_non_reserved_keys_and_plain_values_are_left_as_sent():
    payload = {"a": ({"k": [1, 2, (3, 4)]},), "s": "text", "n": None}
    assert oa._strip_reserved(payload) == payload


@pytest.mark.parametrize("name", list(CASES))
def test_has_reserved_false_after_stripping(name):
    before, _ = CASES[name]
    assert oa._has_reserved(before) is True
    assert oa._has_reserved(oa._strip_reserved(before)) is False


@pytest.mark.parametrize("payload", [{"a": 1}, {"t": ({"k": 1},)}, {"l": [{"k": (1, 2)}]}, {}, {"s": "x"}])
def test_when_has_reserved_is_false_strip_reserved_returns_an_equal_object(payload):
    assert oa._has_reserved(payload) is False
    assert oa._strip_reserved(payload) == payload


@pytest.mark.parametrize("name", list(CASES))
def test_merge_payload_drops_the_nested_reserved_key_when_armed(armed, name):
    before, after = CASES[name]
    assert oa.merge_payload(before) == after


@pytest.mark.parametrize("name", list(CASES))
def test_strip_reserved_unless_asserted_strips_a_tuple_nested_key_when_armed(armed, name):
    before, after = CASES[name]
    assert oa.strip_reserved_unless_asserted(before, {}) == after


@pytest.mark.parametrize("name", list(CASES))
def test_admit_ledger_event_strips_a_tuple_nested_key_for_an_unattributing_caller(armed, name):
    before, after = CASES[name]
    assert oa.admit_ledger_event("kill.agent", before, {}) == after


def test_off_mode_still_returns_the_payload_object_itself(monkeypatch):
    monkeypatch.delenv(oa.ENV_REQUIRE, raising=False)
    monkeypatch.delenv(oa.ENV_REGISTRY, raising=False)
    payload = {"items": ({RES: "m"},)}
    assert oa.merge_payload(payload) is payload and oa.admit_ledger_event("kill.agent", payload, {}) is payload
