"""B101: a payload nested deeper than the bound is refused by OUR check (422 over HTTP, ValueError for a direct appender),
before anything is written. Before, `POST /events` with a payload past pydantic-core's serializer limit was a bare 500
(`PydanticSerializationError` at `model_dump_json`, unmapped; nothing written). That limit is version-dependent: 99
levels on pydantic-core 2.46.4 (an off-pin build), about 252 on the pinned 2.50.1 (integration/constraints.txt). Our
bound (98) is the floor of every version seen, so it always fires first: nothing here asserts the serializer's own
limit, only that it accepts ours.

Depth is counted in nodes, the payload itself as level 1; a scalar value is a node one level below its container; dicts,
lists and tuples nest. No test here depends on the interpreter's recursion limit or the stack: every deep value is built
in a loop, every check walks iteratively, and no RecursionError is asserted."""

from __future__ import annotations

import json
import subprocess
import sys

import pydantic_core
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


def run_bounded(code: str, timeout: float = 60.0) -> str:
    """Run ``code`` in a child interpreter with a hard timeout: a regression that loops (reject_non_finite has no bound
    of its own) is a FAILED assertion here, never a stalled job."""
    try:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        pytest.fail(f"did not return within {timeout} s: a walk of the payload no longer terminates")
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout.strip()


CHILD_PRELUDE = """
import pathlib, tempfile
from field_core.ledger import make_event, reject_too_deep
from sealed_ledger.store import LedgerStore
FIXED = "payload nests too deeply"


def refused(fn):
    try:
        fn()
    except ValueError as exc:
        assert str(exc) == FIXED, str(exc)
        return True
    return False


store = LedgerStore(pathlib.Path(tempfile.mkdtemp()) / "e.jsonl")
"""


def test_a_self_referencing_payload_is_refused_not_looped():
    out = run_bounded(CHILD_PRELUDE + """
a = {}
a["me"] = a
assert refused(lambda: reject_too_deep(a))
assert refused(lambda: make_event("t", a))      # reject_too_deep runs before reject_non_finite (which loops on a cycle)
assert refused(lambda: store.append("t", a))
print("refused")
""")
    assert out == "refused"


def test_a_shared_subobject_dag_is_refused_by_the_visit_budget_not_walked_per_path():
    """two references per level, 40 levels: about 2**40 paths. 40 levels is inside the depth bound (41 nodes), so only the
    visit budget stops it; in a child with a hard timeout."""
    out = run_bounded(CHILD_PRELUDE + """
v = {}
for _ in range(40):
    v = {"a": v, "b": v}
assert refused(lambda: reject_too_deep(v))
assert refused(lambda: make_event("t", v))
assert refused(lambda: store.append("t", v))
print("refused")
""", timeout=60.0)
    assert out == "refused"


def test_a_small_shared_subobject_dag_is_still_accepted():
    v: dict = {}
    for _ in range(10):                       # 2**10 paths, 2**11 - 1 containers
        v = {"a": v, "b": v}
    reject_too_deep(v)


def test_the_budget_counts_containers_not_scalars(monkeypatch):
    import field_core.ledger as ledger_mod

    monkeypatch.setattr(ledger_mod, "MAX_PAYLOAD_CONTAINERS", 10)
    reject_too_deep({"k": list(range(5000))})                       # 2 containers, 5000 scalars
    reject_too_deep({"k": [{} for _ in range(8)]})                  # 1 + 1 + 8 = 10
    with pytest.raises(ValueError) as exc:
        reject_too_deep({"k": [{} for _ in range(9)]})              # 11
    assert str(exc.value) == FIXED


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


# --- a refused payload from a direct appender never takes the writer lock (reviewer C2) ---------------------------

def _snapshot(directory):
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir()) if p.is_file()}


@pytest.mark.parametrize("payload,why", [
    (make(MAX_PAYLOAD_DEPTH + 1), "too deep"),
    ({"a": {"b": float("nan")}}, "non-finite"),
])
def test_a_refused_direct_append_never_takes_the_writer_lock_or_reconciles(tmp_path, monkeypatch, payload, why):
    path = tmp_path / "events.jsonl"
    store = LedgerStore(path)
    store.append("first", {"a": 1}, agent_id="a")
    before = _snapshot(tmp_path)                                    # the event file, its lock and journal files if any

    def boom(*a, **k):
        raise AssertionError("a refused payload reached the writer lock or the reconciliation")

    monkeypatch.setattr(LedgerStore, "_writer", boom)
    monkeypatch.setattr(LedgerStore, "_ensure_fresh_locked", boom)
    with pytest.raises(ValueError):
        store.append("t", payload, agent_id="a")
    assert _snapshot(tmp_path) == before                           # every file byte-identical, none added
    monkeypatch.undo()
    assert LedgerStore(path).verify().ok


# --- the probe: the installed serializer must accept our bound (reviewer's and the controller's item b) --------------

def _serializes(levels: int) -> bool:
    event = LedgerEvent(event_id="e", ts="2026-01-01T00:00:00+00:00", event_type="t", payload=make(levels),
                        prev_hash="0" * 64, hash="0" * 64)
    try:
        event.model_dump_json()
    except ValueError:                                              # PydanticSerializationError is a ValueError
        return False
    return True


def probed_serializer_limit(ceiling: int = 300) -> int:
    """the deepest payload (in nodes) the installed pydantic-core serializes, found by bisection up to ``ceiling``"""
    lo, hi = 2, ceiling
    if _serializes(hi):
        return hi
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if _serializes(mid):
            lo = mid
        else:
            hi = mid - 1
    return lo


def test_the_installed_serializer_limit_is_not_below_our_bound():
    """No assertion on the exact limit (98 on pydantic-core 2.46.4, about 252 on the pinned 2.50.1): only that it is not
    below ours, with the numbers in the message so a version refresh that lowers or raises it is visible in the log."""
    limit = probed_serializer_limit()
    assert limit >= MAX_PAYLOAD_DEPTH, (
        f"the installed serializer (pydantic-core {pydantic_core.__version__}) stops at {limit} nodes, below our bound "
        f"{MAX_PAYLOAD_DEPTH}: payloads between {limit + 1} and {MAX_PAYLOAD_DEPTH} would be refused by the serializer "
        "with a bare 500 again; lower MAX_PAYLOAD_DEPTH")
