"""B101: a payload nested deeper than the bound is refused by OUR check (422 over HTTP, ValueError for a direct appender),
before anything is written. Before, `POST /events` with a payload 99 levels deep was a bare 500: pydantic-core's JSON
serializer refuses depth 99 at `model_dump_json` (`PydanticSerializationError`, unmapped), nothing written.

Depth is counted in nodes, the payload itself as level 1; a scalar value is a node one level below its container; dicts,
lists and tuples nest. No test here depends on the interpreter's recursion limit or the stack: every deep value is built
in a loop, every check walks iteratively, and no RecursionError is asserted."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from field_core.ledger import MAX_PAYLOAD_DEPTH, LedgerEvent, make_event, reject_too_deep
from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore

HDR = {"content-type": "application/json"}
FIXED = "payload nests too deeply"


def make(levels: int, kind: str = "dict", leaf=1):
    """a payload whose deepest node is at ``levels`` (the payload dict is level 1); ``leaf`` is that deepest node"""
    v = leaf
    for i in range(levels - 2, -1, -1):
        wrap_dict = kind == "dict" or (kind == "mixed" and i % 2 == 0)
        v = {"k": v} if (i == 0 or wrap_dict) else [v]        # the payload itself is always a dict
    return v


def nodes(value) -> int:
    best, stack = 0, [(value, 1)]
    while stack:
        v, level = stack.pop()
        best = max(best, level)
        if isinstance(v, dict):
            stack.extend((c, level + 1) for c in v.values())
        elif isinstance(v, (list, tuple)):
            stack.extend((c, level + 1) for c in v)
    return best


SHAPES = [(kind, leaf) for kind in ("dict", "list", "mixed") for leaf in (1, "x", None, {}, [])]


def test_the_bound_is_98_nodes_and_the_helper_builds_what_it_says():
    assert MAX_PAYLOAD_DEPTH == 98
    for kind, leaf in SHAPES:
        for levels in (2, 50, 98, 99):
            assert nodes(make(levels, kind, leaf)) == levels, (kind, leaf, levels)


@pytest.mark.parametrize("kind,leaf", SHAPES)
def test_98_is_accepted_and_99_is_refused_with_the_fixed_text(kind, leaf):
    reject_too_deep(make(98, kind, leaf))
    reject_too_deep(make(97, kind, leaf))
    with pytest.raises(ValueError) as exc:
        reject_too_deep(make(99, kind, leaf))
    assert str(exc.value) == FIXED


def test_a_tuple_nests_like_a_list_and_a_scalar_is_a_level():
    deep = ("x",)
    for _ in range(98):
        deep = (deep,)                       # 99 levels with the string inside the innermost tuple
    with pytest.raises(ValueError):
        reject_too_deep({"k": deep})
    reject_too_deep({"k": 1})                # level 2
    # the scalar under a level-98 container is level 99: refused; an EMPTY container at level 98 is accepted
    reject_too_deep(make(98, "dict", {}))
    with pytest.raises(ValueError):
        reject_too_deep(make(99, "dict", 1))


def test_a_large_depth_built_in_a_loop_is_refused_without_recursion():
    big = {}
    cur = big
    for _ in range(3000):
        nxt: dict = {}
        cur["k"] = nxt
        cur = nxt
    with pytest.raises(ValueError) as exc:
        reject_too_deep(big)
    assert str(exc.value) == FIXED


def test_a_self_referencing_payload_is_refused_not_looped():
    a: dict = {}
    a["me"] = a
    with pytest.raises(ValueError) as exc:
        reject_too_deep(a)
    assert str(exc.value) == FIXED
    with pytest.raises(ValueError):
        make_event("t", a)                    # reject_too_deep runs before reject_non_finite (which would loop on a cycle)


def test_the_refusal_never_carries_a_key_or_a_value():
    secret = "SECRETKEY-123"
    payload = make(99)
    inner = payload
    while isinstance(inner.get("k"), dict):
        inner = inner["k"]
    inner[secret] = secret
    with pytest.raises(ValueError) as exc:
        reject_too_deep(payload)
    assert secret not in str(exc.value) and str(exc.value) == FIXED


def test_make_event_refuses_99_before_building_anything():
    with pytest.raises(ValueError) as exc:
        make_event("t", make(99))
    assert str(exc.value) == FIXED
    assert make_event("t", make(98)).payload                       # 98 builds


# --- our bound must not exceed the serializer's: this fails if pydantic's own limit ever drops below ours ------------

@pytest.mark.parametrize("kind,leaf", SHAPES)
def test_the_serializer_still_accepts_our_bound(kind, leaf):
    event = make_event("t", make(MAX_PAYLOAD_DEPTH, kind, leaf))
    line = event.model_dump_json()                                 # pydantic-core: the limit that used to be the 500
    assert LedgerEvent.model_validate(json.loads(line)) == event   # and it reads back


@pytest.mark.parametrize("kind", ["dict", "list", "mixed"])
def test_the_store_seals_our_bound_and_the_chain_verifies(tmp_path, kind):
    store = LedgerStore(tmp_path / "events.jsonl")
    store.append("t", make(MAX_PAYLOAD_DEPTH, kind, 1), agent_id="a")
    assert LedgerStore(tmp_path / "events.jsonl").verify().ok


def test_the_store_refuses_99_and_writes_nothing(tmp_path):
    path = tmp_path / "events.jsonl"
    store = LedgerStore(path)
    store.append("first", {"a": 1}, agent_id="a")
    before = path.read_bytes()
    with pytest.raises(ValueError) as exc:
        store.append("t", make(MAX_PAYLOAD_DEPTH + 1), agent_id="a")
    assert str(exc.value) == FIXED
    assert path.read_bytes() == before and LedgerStore(path).verify().ok


# --- HTTP --------------------------------------------------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(store=LedgerStore(tmp_path / "events.jsonl")), raise_server_exceptions=False)


def post(client, payload):
    return client.post("/events", content=json.dumps({"event_type": "x", "payload": payload}), headers=HDR)


def test_http_98_is_201_and_99_is_a_422_with_no_echo_and_nothing_written(client):
    assert post(client, make(98)).status_code == 201
    r = post(client, make(99))
    assert r.status_code == 422, r.text
    detail = r.json()["detail"][0]          # the app's 422 handler drops the input and shortens a ValueError to "Value error"
    assert detail["loc"] == ["body", "payload"] and "input" not in detail and '"k"' not in r.text
    assert len(client.get("/events").json()) == 1 and client.get("/verify").json()["ok"] is True


@pytest.mark.parametrize("kind", ["list", "mixed"])
def test_http_lists_count_too(client, kind):
    assert post(client, make(98, kind)).status_code == 201
    assert post(client, make(99, kind)).status_code == 422


def test_http_a_wide_shallow_payload_is_untouched(client):
    wide = {"a%d" % i: [i, {"b": [i]}] for i in range(500)}
    assert post(client, wide).status_code == 201
