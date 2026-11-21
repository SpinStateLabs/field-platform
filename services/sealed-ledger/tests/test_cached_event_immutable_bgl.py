"""B-GL-ledger-cache-immutable: the T7 parse cache hands every events() caller the SAME LedgerEvent objects, so
they must be immutable: a caller cannot make the next verify() of unchanged bytes report a tamper. Each test
names the behaviour it pins; the poisoning end-to-end is test_verify_inputs_cache_key_bgl.py::test_i13b."""

from __future__ import annotations

import copy
import json

import pytest

from field_core.ledger import LedgerEvent
from sealed_ledger.store import LedgerStore

from ledger_c2_support import fill


def _store(tmp_path, n=5):
    s = LedgerStore(tmp_path / "events.jsonl")
    for i in range(n):
        s.append("t", {"n": i, "nested": {"k": [1, 2, {"z": 1}]}}, agent_id="a")
    assert s.verify().ok
    return s


@pytest.mark.parametrize("field", ["event_id", "ts", "event_type", "agent_id", "prev_hash", "hash", "signature"])
def test_assigning_an_attribute_of_a_returned_event_is_refused(tmp_path, field):
    s = _store(tmp_path)
    ev = s.events()[0]
    with pytest.raises(Exception):
        setattr(ev, field, "x")
    s.append("t", {"more": 1}, agent_id="a")
    assert s.verify().ok is True


def test_mutating_payload_at_any_depth_is_refused(tmp_path):
    s = _store(tmp_path)
    p = s.events()[0].payload
    for mutate in (lambda: p.__setitem__("n", 9), lambda: p.pop("n"), lambda: p.update(n=9),
                   lambda: p.setdefault("q", 1), lambda: p.clear(), lambda: p.popitem(),
                   lambda: p["nested"].__setitem__("k", 1), lambda: p["nested"]["k"].append(1),
                   lambda: p["nested"]["k"].__setitem__(0, 9), lambda: p["nested"]["k"][2].__setitem__("z", 2),
                   lambda: p["nested"]["k"].sort(), lambda: p["nested"]["k"].extend([1]),
                   lambda: p.__delitem__("n"), lambda: p.__ior__({"n": 1})):
        with pytest.raises(TypeError):
            mutate()
    s.append("t", {"more": 1}, agent_id="a")
    assert s.verify().ok is True and s.verify() == LedgerStore(s.path).verify()


def test_a_second_events_call_after_an_attempted_mutation_is_unchanged(tmp_path):
    s = _store(tmp_path)
    before = [e.model_dump() for e in s.events()]
    try:
        s.events()[0].payload["n"] = 999
    except TypeError:
        pass
    assert [e.model_dump() for e in s.events()] == before


def test_events_stay_equal_to_plainly_built_events_and_serialize_the_same(tmp_path):
    s = _store(tmp_path)
    cached = s.events()
    fresh = LedgerStore(s.path).events()       # a separate store: its own parse
    assert cached == fresh
    for e in cached:
        plain = LedgerEvent.model_validate(json.loads(e.model_dump_json()))
        assert e == plain and plain == e and type(e) is LedgerEvent
        assert e.model_dump() == plain.model_dump() and e.model_dump_json() == plain.model_dump_json()
        assert type(e.model_dump()["payload"]) is dict          # a dump is plain, mutable data
        assert json.dumps(e.payload, sort_keys=True) == json.dumps(plain.payload, sort_keys=True)


def test_events_are_not_hashable_as_before(tmp_path):
    s = _store(tmp_path, 1)
    with pytest.raises(TypeError):
        hash(s.events()[0])
    with pytest.raises(TypeError):
        hash(LedgerEvent(event_id="1", ts="t", event_type="x", prev_hash="p", hash="h"))


def test_copies_of_an_event_are_ordinary_mutable_data(tmp_path):
    s = _store(tmp_path)
    ev = s.events()[0]
    for dup in (copy.deepcopy(ev), copy.copy(ev), ev.model_copy(deep=True), LedgerEvent(**ev.model_dump())):
        assert dup == ev
        dup_payload = dup.payload
        assert dup_payload == ev.payload
    d = copy.deepcopy(ev.payload)
    d["n"] = 9                                  # a deep copy of the payload is the caller's own dict
    d["nested"]["k"].append(1)
    assert s.events()[0].payload["n"] == 0


def test_a_caller_built_event_is_not_aliased_to_the_callers_dict():
    payload = {"a": [1]}
    ev = LedgerEvent(event_id="1", ts="t", event_type="x", prev_hash="p", hash="h", payload=payload)
    payload["a"].append(2)
    payload["b"] = 1
    assert ev.payload == {"a": [1]}


def test_the_default_payload_is_per_event_and_empty():
    a = LedgerEvent(event_id="1", ts="t", event_type="x", prev_hash="p", hash="h")
    b = LedgerEvent(event_id="2", ts="t", event_type="x", prev_hash="p", hash="h")
    assert a.payload == {} and a.payload is not b.payload
