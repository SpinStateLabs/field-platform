"""B-GL-ledger-cache-immutable (option C): the T7 parse cache keeps its own plain LedgerEvent objects PRIVATE and
hands callers (events(), iter_events(), snapshot()) read-only copies, built lazily once per cached event. A caller
cannot change one, so it cannot corrupt the cache, make the next verify() of unchanged bytes report a tamper, or
MASK a real one. LedgerEvent itself stays plain, so a cache miss pays no freeze. Each test names the behaviour it
pins; the poisoning end-to-end is test_verify_inputs_cache_key_bgl.py::test_i13b."""

from __future__ import annotations

import copy
import json

import pytest

from field_core import ledger as _ledger_mod
from field_core.ledger import LedgerEvent, ReadOnlyLedgerEvent
import sealed_ledger.store as _store_mod
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
        assert e == plain and plain == e and isinstance(e, LedgerEvent) and type(e) is ReadOnlyLedgerEvent and type(plain) is LedgerEvent
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


def test_the_default_payload_is_per_event_and_empty():
    a = LedgerEvent(event_id="1", ts="t", event_type="x", prev_hash="p", hash="h")
    b = LedgerEvent(event_id="2", ts="t", event_type="x", prev_hash="p", hash="h")
    assert a.payload == {} and a.payload is not b.payload


def test_every_reinitialisation_route_into_a_payload_is_refused(tmp_path):
    """B-FIX-PR1106: ``payload.__init__(...)`` on a dict/list SUBCLASS rewrites it in place through the normal
    Python API (no ctypes, no object.__setattr__), so every mutator is closed, not just the usual ones."""
    s = _store(tmp_path)
    p = s.events()[0].payload
    for mutate in (lambda: p.__init__(n=9), lambda: p.__init__({"n": 9}), lambda: p["nested"].__init__(k=1),
                   lambda: p["nested"]["k"].__init__([9]), lambda: p["nested"]["k"][2].__init__(z=2)):
        with pytest.raises(TypeError):
            mutate()
    assert [e.model_dump() for e in s.events()] == [e.model_dump() for e in LedgerStore(s.path).events()]
    s.append("t", {"more": 1}, agent_id="a")
    assert s.verify().ok is True and s.verify() == LedgerStore(s.path).verify()


def test_a_caller_cannot_mask_a_tamper_through_the_cache(tmp_path):
    """The reviewer's masking reproduction (PR 1095, roley.reviewer): tamper one event on disk, then try to
    put the original payload back through the cached event and append. Every attempt must raise, and this
    process's verify() must equal a fresh store's (not ok) before and after the append."""
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    for i in range(5):
        s.append("t", {"n": i, "nested": {"k": [1, 2]}}, agent_id="a")
    s.events()                                                   # warm: the clean parse is cached
    lines = p.read_text().splitlines()
    doc = json.loads(lines[2])
    original = copy.deepcopy(doc["payload"])
    doc["payload"]["n"] = 777                                    # a real tamper on disk
    lines[2] = json.dumps(doc)
    p.write_text("\n".join(lines) + "\n")
    assert LedgerStore(p).verify().ok is False
    cached = s.events()[2]                                       # the cache still holds the clean parse or the tampered one
    for restore in (lambda: cached.payload.__setitem__("n", original["n"]), lambda: cached.payload.update(original),
                    lambda: cached.payload.__init__(**original), lambda: setattr(cached, "payload", original)):
        with pytest.raises(Exception):
            restore()
    fresh = LedgerStore(p).verify()
    assert s.verify() == fresh and fresh.ok is False
    try:
        s.append("t", {"more": 1}, agent_id="a")
    except Exception:
        pass                                                     # an append onto a tampered chain may refuse
    assert s.verify() == LedgerStore(p).verify()
    assert s.verify().ok is False


# ---- option C: what stays plain, what stays private, what is shared ---------------------------------------------


def test_ledger_event_itself_is_still_plain_and_mutable():
    """Validation cost is unchanged: LedgerEvent is not frozen and its payload is the plain dict it always was
    (no freeze on a cache miss). Only ReadOnlyLedgerEvent (the hand-out type) is read-only."""
    assert LedgerEvent.model_config.get("frozen") is not True
    assert ReadOnlyLedgerEvent.model_config.get("frozen") is True
    ev = LedgerEvent.model_validate({"event_id": "1", "ts": "t", "event_type": "x", "prev_hash": "p", "hash": "h",
                                     "payload": {"a": {"b": [1]}}})
    assert type(ev.payload) is dict and type(ev.payload["a"]) is dict and type(ev.payload["a"]["b"]) is list
    ev.payload["a"]["b"].append(2)
    ev.hash = "h2"
    assert ev.hash == "h2" and ev.payload == {"a": {"b": [1, 2]}}


def test_the_cache_keeps_plain_private_events_and_hands_out_read_only_copies(tmp_path):
    s = _store(tmp_path)
    handed = s.events()
    (path, (raw, kept, twins)), = s._parse_cache.items()
    assert len(kept) == len(handed) == 5
    for private, out in zip(kept, handed):
        assert type(private) is LedgerEvent and type(private.payload) is dict       # the cache's own: plain
        assert type(out) is ReadOnlyLedgerEvent and out is not private              # the caller's: a copy
        assert out.payload is not private.payload and out == private
        assert out.payload["nested"] is not private.payload["nested"]
    assert all(t is o for t, o in zip(twins, handed))                                # the twins ARE what was handed out


def test_iter_events_and_snapshot_hand_out_read_only_copies_too(tmp_path):
    s = _store(tmp_path)
    for ev in list(s.iter_events()) + [e for _, e in s.snapshot().indexed_events()]:
        assert type(ev) is ReadOnlyLedgerEvent
        with pytest.raises(TypeError):
            ev.payload["n"] = 9
        with pytest.raises(Exception):
            ev.hash = "x"
    (_, (_, kept, _)), = s._parse_cache.items()
    assert all(type(e) is LedgerEvent for e in kept)


def test_verify_and_export_walk_the_private_plain_events(tmp_path):
    s = _store(tmp_path)
    s._parse_cache.clear()
    assert s.verify().ok
    (_, (_, kept, twins)), = s._parse_cache.items()
    assert all(type(e) is LedgerEvent for e in kept) and twins == []                # verify freezes nothing


def test_the_returned_list_is_the_callers_own_but_the_events_are_shared_and_read_only(tmp_path):
    s = _store(tmp_path)
    a, b = s.events(), s.events()
    assert a is not b and a == b and all(x is y for x, y in zip(a, b))   # shared immutable objects, own lists
    a.pop()
    a.append("junk")
    a.clear()
    assert len(s.events()) == 5 and all(type(e) is ReadOnlyLedgerEvent for e in s.events())


def test_an_append_extends_the_read_only_twins_and_keeps_the_earlier_ones(tmp_path):
    s = _store(tmp_path)
    before = s.events()
    s.append("t", {"more": 1}, agent_id="a")
    after = s.events()
    assert len(after) == 6 and all(x is y for x, y in zip(before, after))
    assert after == LedgerStore(s.path).events() and s.verify() == LedgerStore(s.path).verify()
    assert after[5].payload == {"more": 1}


def test_a_changed_file_gets_fresh_twins_not_stale_ones(tmp_path):
    p = tmp_path / "events.jsonl"
    s = LedgerStore(p)
    for i in range(3):
        s.append("t", {"n": i}, agent_id="a")
    old = s.events()
    lines = p.read_text().splitlines()
    doc = json.loads(lines[1])
    doc["payload"]["n"] = 41                                     # a same-length in-place edit on disk
    lines[1] = json.dumps(doc)
    p.write_text("\n".join(lines) + "\n")
    new = s.events()
    assert new[1].payload == {"n": 41} and old[1].payload == {"n": 1}
    assert new == LedgerStore(p).events() and s.verify() == LedgerStore(p).verify()


def test_a_segment_too_big_to_cache_is_still_handed_out_read_only(tmp_path, monkeypatch):
    monkeypatch.setattr(_store_mod, "PARSE_CACHE_MAX_BYTES", 10)
    s = _store(tmp_path)
    assert s._parse_cache == {}
    for ev in s.events():
        assert type(ev) is ReadOnlyLedgerEvent
        with pytest.raises(TypeError):
            ev.payload["nested"]["k"].append(1)
    assert s.verify().ok


def test_read_only_event_equals_a_plain_event_on_either_side_and_is_unhashable():
    plain = LedgerEvent(event_id="1", ts="t", event_type="x", prev_hash="p", hash="h", payload={"a": [1]})
    ro = ReadOnlyLedgerEvent.of(plain)
    assert ro == plain and plain == ro and not (ro != plain) and not (plain != ro)
    assert ro != LedgerEvent(event_id="2", ts="t", event_type="x", prev_hash="p", hash="h", payload={"a": [1]})
    with pytest.raises(TypeError):
        hash(ro)
    plain.payload["a"].append(2)                                  # the source is not aliased by the copy
    assert ro.payload == {"a": [1]}
    with pytest.raises(Exception):
        ro.payload = {}
