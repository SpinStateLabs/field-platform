"""B-GL-ledger-cache-immutable (option C): the T7 parse cache keeps its own plain LedgerEvent objects PRIVATE and
hands callers (events(), iter_events(), snapshot()) read-only copies, built lazily once per cached event. A caller
cannot change one, so it cannot corrupt the cache, make the next verify() of unchanged bytes report a tamper, or
MASK a real one. LedgerEvent itself stays plain, so a cache miss pays no freeze. Each test names the behaviour it
pins; the poisoning end-to-end is test_verify_inputs_cache_key_bgl.py::test_i13b."""

from __future__ import annotations

import copy
import pickle
import threading
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


def test_of_builds_exactly_what_pydantic_model_construct_builds():
    """``of`` sets pydantic's instance slots directly (cheaper than model_construct); pin it to the public API."""
    plain = LedgerEvent(event_id="1", ts="t", event_type="x", prev_hash="p", hash="h", signature="s",
                        payload={"a": [1, {"b": 2}]})
    frozen_payload = ReadOnlyLedgerEvent.of(plain).payload
    ref = ReadOnlyLedgerEvent.model_construct(_fields_set=set(plain.model_fields_set),
                                              **{**plain.__dict__, "payload": frozen_payload})
    got = ReadOnlyLedgerEvent.of(plain)
    assert got == ref and got.model_fields_set == ref.model_fields_set == plain.model_fields_set
    assert got.__pydantic_extra__ is None and got.__pydantic_private__ is None
    assert got.model_dump() == ref.model_dump() == plain.model_dump()
    assert got.model_dump_json() == ref.model_dump_json() == plain.model_dump_json()
    assert got.model_fields_set is not plain.model_fields_set
    assert set(got.__dict__) == set(LedgerEvent.model_fields)
    assert got.model_copy().payload == got.payload and copy.deepcopy(got) == got


def test_a_cache_miss_and_verify_build_no_read_only_copies(tmp_path, monkeypatch):
    """The point of option C: parsing and verifying cost what they did before. No ReadOnlyLedgerEvent is built
    by a cold verify(), a warm verify(), or an append; only a hand-out builds them, once per event."""
    s = _store(tmp_path)
    s._parse_cache.clear()
    s._verify_cache = None
    calls = []
    real = ReadOnlyLedgerEvent.of.__func__
    monkeypatch.setattr(ReadOnlyLedgerEvent, "of", classmethod(lambda cls, ev: (calls.append(1), real(cls, ev))[1]))
    assert s.verify().ok                                         # cold: parse + walk
    s._verify_cache = None
    assert s.verify().ok                                         # warm parse, re-walk
    s.append("t", {"more": 1}, agent_id="a")
    assert s.verify().ok
    assert calls == []
    assert len(s.events()) == 6 and len(calls) == 6              # the first hand-out copies each event once
    s.events(), s.events(), list(s.iter_events())
    assert len(calls) == 6                                       # later hand-outs reuse them
    s.append("t", {"more": 2}, agent_id="a")
    assert len(s.events()) == 7 and len(calls) == 7              # only the new tail is copied


def test_the_list_inside_a_returned_snapshot_is_the_callers_own(tmp_path):
    """snapshot() hands out the Snapshot object, so the lists in ``segments`` must not be the cache's own twin list."""
    s = _store(tmp_path)
    snap1, snap2 = s.snapshot(), s.snapshot()
    l1, l2 = snap1.segments[-1][1], snap2.segments[-1][1]
    assert l1 is not l2 and l1 == l2 and all(a is b for a, b in zip(l1, l2))
    junk = object()
    l1[0] = junk
    l1.pop()
    l2.clear()
    assert [e.payload["n"] for e in s.events()] == [0, 1, 2, 3, 4]
    assert [e.payload["n"] for _, e in s.snapshot().indexed_events()] == [0, 1, 2, 3, 4]


def test_events_with_a_limit_hands_out_read_only_events_warm_and_cold(tmp_path, monkeypatch):
    # B-GL-events-limit-cheap's tail path (_events_tail) reads the cache itself: warm it must use the twins, cold it
    # must wrap what it parses; a plain event here would be the private cached object (warm) or break the contract.
    s = _store(tmp_path, 6)
    warm = s.events(limit=3)
    assert len(warm) == 3 and all(type(e) is ReadOnlyLedgerEvent for e in warm)
    with pytest.raises(TypeError):
        warm[0].payload["n"] = 99
    before = [e.model_dump() for e in s.events()]
    assert s.verify().ok is True
    cold = LedgerStore(s.path)
    cold._parse_cache.clear()
    monkeypatch.setattr(_store_mod.LedgerStore, "EVENTS_TAIL_WINDOW_BYTES", 1 << 20)
    got = cold.events(limit=3)
    assert len(got) == 3 and all(type(e) is ReadOnlyLedgerEvent for e in got)
    with pytest.raises(TypeError):
        got[0].payload["nested"]["k"].append(1)
    assert [e.model_dump() for e in s.events()] == before


# --- B-FIX-PR1106-C1 (don.reviewer's delta verdict on 044a39e): the twin is SHARED by every later caller, so a
# --- rewrite of a handed-out event through an ordinary method changes what everyone after it receives.

def _forged_fields(ev, **over):
    return {**ev.model_dump(), **over}


def _later_caller_sees_the_original(s, original_dump):
    assert [e.model_dump() for e in s.events()] == original_dump
    assert all(type(e) is ReadOnlyLedgerEvent for e in s.events())
    assert s.verify().ok is True and s.verify() == LedgerStore(s.path).verify()


def test_route_init_reinitialisation_of_a_handed_out_event_is_refused(tmp_path):
    s = _store(tmp_path)
    original = [e.model_dump() for e in s.events()]
    ev = s.events()[0]
    with pytest.raises(TypeError):
        ev.__init__(**_forged_fields(ev, event_type="X1"))
    with pytest.raises(TypeError):
        ReadOnlyLedgerEvent.__init__(ev, **_forged_fields(ev, event_type="X1"))
    _later_caller_sees_the_original(s, original)


def test_route_setstate_on_a_handed_out_event_is_refused(tmp_path):
    s = _store(tmp_path)
    original = [e.model_dump() for e in s.events()]
    ev = s.events()[0]
    state = ev.__getstate__()
    forged = {**state, "__dict__": {**state["__dict__"], "event_type": "X2"}}
    with pytest.raises(TypeError):
        ev.__setstate__(forged)
    _later_caller_sees_the_original(s, original)


def test_route_class_swap_on_a_handed_out_event_is_refused(tmp_path):
    s = _store(tmp_path)
    original = [e.model_dump() for e in s.events()]
    ev = s.events()[0]
    with pytest.raises(TypeError):
        ev.__class__ = LedgerEvent
    with pytest.raises(TypeError):
        object.__setattr__(ev, "__class__", LedgerEvent)
    assert type(ev) is ReadOnlyLedgerEvent
    with pytest.raises(Exception):
        ev.event_type = "X3"
    _later_caller_sees_the_original(s, original)


def test_underscore_names_and_the_instance_dict_cannot_be_assigned_either(tmp_path):
    """pydantic sends ``_name`` assignments past ``frozen`` to ``object.__setattr__``; that includes ``__dict__``."""
    s = _store(tmp_path)
    original = [e.model_dump() for e in s.events()]
    ev = s.events()[0]
    for assign in (lambda: setattr(ev, "_x", 1), lambda: setattr(ev, "__dict__", {})):
        with pytest.raises(Exception):
            assign()
    _later_caller_sees_the_original(s, original)
    assert "_x" not in ev.__dict__


def test_the_refusals_leave_construction_isinstance_and_copies_working(tmp_path):
    s = _store(tmp_path)
    ev = s.events()[0]
    assert isinstance(ev, LedgerEvent) and isinstance(ev, ReadOnlyLedgerEvent)
    assert ev.__class__ is ReadOnlyLedgerEvent and type(ev) is ReadOnlyLedgerEvent
    plain = LedgerEvent(**ev.model_dump())
    built = ReadOnlyLedgerEvent(**ev.model_dump())            # one construction call is still fine
    assert built == ev and type(built) is ReadOnlyLedgerEvent
    with pytest.raises(Exception):
        built.event_type = "Y"
    assert ReadOnlyLedgerEvent.of(plain) == ev
    assert ReadOnlyLedgerEvent.model_validate(ev.model_dump()) == ev
    assert ReadOnlyLedgerEvent.model_validate_json(ev.model_dump_json()) == ev
    assert ev.model_copy() == ev and ev.model_copy(update={"agent_id": "b"}).agent_id == "b"
    # pickle / copy / deepcopy give DETACHED plain data (a plain LedgerEvent), never the shared twin
    for dup in (pickle.loads(pickle.dumps(ev)), pickle.loads(pickle.dumps(ev, protocol=2)),
                copy.copy(ev), copy.deepcopy(ev), ev.model_copy(deep=True)):
        assert dup == ev and dup is not ev
        assert isinstance(dup, LedgerEvent)
        d = copy.deepcopy(dup.payload)
        d["n"] = 99
    for dup in (pickle.loads(pickle.dumps(ev)),):
        assert type(dup) is LedgerEvent
        dup.event_type = "mine"                                  # mutable: it is the caller's own
        dup.payload["n"] = 99
    assert s.events()[0].event_type == "t" and s.events()[0].payload["n"] == 0


def test_a_nested_payload_list_refuses_inplace_add_and_multiply(tmp_path):
    """N1 (kills the mutant 'list __iadd__ allowed'): ``+=`` / ``*=`` on a list inside the payload."""
    s = _store(tmp_path)
    p = s.events()[0].payload
    lst = p["nested"]["k"]

    def iadd():
        nonlocal lst
        lst += [9]

    def imul():
        nonlocal lst
        lst *= 2

    for op in (iadd, imul):
        with pytest.raises(TypeError):
            op()
    assert s.events()[0].payload["nested"]["k"] == [1, 2, {"z": 1}]


def test_two_readers_extending_the_twin_list_together_hand_out_aligned_events(tmp_path, monkeypatch):
    """N3 (kills the mutant 'twin-extend race guard dropped'): two threads both see an empty twin list and both
    build copies; a Barrier inside ``ReadOnlyLedgerEvent.of`` makes them overlap deterministically (no sleeps).
    Without the guard both extend, the twin list is longer than the parse, and after the next append the
    events handed out are misaligned with the ledger."""
    s = LedgerStore(tmp_path / "events.jsonl")
    for i in range(3):
        s.append("t", {"n": i}, agent_id="a")
    assert s.verify().ok                       # parse cached, twin list empty
    monkeypatch.setattr(s, "_gate_sem", None)  # the heavy-read gate would serialise the two readers
    barrier = threading.Barrier(2)
    seen = threading.local()
    real_of = ReadOnlyLedgerEvent.of

    def hooked_of(ev):
        if not getattr(seen, "waited", False):
            seen.waited = True
            barrier.wait(timeout=20)           # both readers are inside the copy loop before either finishes
        return real_of(ev)

    monkeypatch.setattr(ReadOnlyLedgerEvent, "of", staticmethod(hooked_of))
    results, errors = [], []

    def reader():
        try:
            results.append(s.events())
        except BaseException as exc:           # a broken barrier must fail the test, not hang it
            errors.append(exc)

    threads = [threading.Thread(target=reader) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not errors and not any(t.is_alive() for t in threads)
    monkeypatch.undo()
    fresh = LedgerStore(s.path).events()
    for got in results:
        assert got == fresh
    s.append("t", {"n": 3}, agent_id="a")
    fresh = LedgerStore(s.path).events()
    assert len(fresh) == 4 and s.events() == fresh
    assert [e.payload["n"] for e in s.events()] == [0, 1, 2, 3]


def _orderable_store(tmp_path):
    s = LedgerStore(tmp_path / "events.jsonl")
    s.append("t", {"o": [3, 1, 2], "d": {"b": 1, "a": 2}}, agent_id="a")
    assert s.verify().ok
    return s


def test_every_list_mutator_is_refused_on_an_orderable_payload_list_and_leaves_it_unchanged(tmp_path):
    """PR 1106 review C2 (mutants K1 sort, K2 del lst[0], K4 reverse): the earlier tests used a list holding a dict,
    on which sort() fails with TypeError anyway, so a mutant that allowed it survived. An all-int list sorts for real."""
    s = _orderable_store(tmp_path)
    lst = s.events()[0].payload["o"]

    def del_first():
        del lst[0]

    def del_slice():
        del lst[:1]

    ops = [lambda: lst.sort(), lambda: lst.sort(reverse=True), lambda: lst.reverse(), del_first, del_slice,
           lambda: lst.append(4), lambda: lst.extend([4]), lambda: lst.insert(0, 4), lambda: lst.pop(),
           lambda: lst.remove(3), lambda: lst.clear(), lambda: lst.__setitem__(0, 9)]
    for op in ops:
        with pytest.raises(TypeError):
            op()
    assert s.events()[0].payload["o"] == [3, 1, 2]
    assert lst == [3, 1, 2]


def test_every_dict_mutator_is_refused_and_leaves_the_payload_unchanged(tmp_path):
    s = _orderable_store(tmp_path)
    d = s.events()[0].payload["d"]

    def del_key():
        del d["a"]

    ops = [del_key, lambda: d.clear(), lambda: d.pop("a"), lambda: d.popitem(), lambda: d.setdefault("z", 1),
           lambda: d.update({"z": 1}), lambda: d.__setitem__("a", 9), lambda: d.__init__(a=9)]
    for op in ops:
        with pytest.raises(TypeError):
            op()
    assert d == {"b": 1, "a": 2}


def test_a_copy_of_a_payload_dict_or_list_is_a_plain_detached_mutable_one(tmp_path):
    """PR 1106 review C2 (mutants K3 dict copy() returns self, K5 list copy() returns self)."""
    s = _orderable_store(tmp_path)
    payload = s.events()[0].payload
    dc = payload.copy()
    assert type(dc) is dict and dc is not payload
    dc["new"] = 1
    dc["d"] = "replaced"
    assert "new" not in s.events()[0].payload and s.events()[0].payload["d"] == {"b": 1, "a": 2}
    inner = payload["d"].copy()
    assert type(inner) is dict and inner is not payload["d"]
    inner["x"] = 1
    assert "x" not in s.events()[0].payload["d"]
    lst = payload["o"]
    lc = lst.copy()
    assert type(lc) is list and lc is not lst
    lc.sort()
    lc.append(9)
    del lc[0]
    assert s.events()[0].payload["o"] == [3, 1, 2]
