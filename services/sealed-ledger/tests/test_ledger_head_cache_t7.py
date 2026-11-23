"""T7: the ledger-head parse cache. One /attest/pack issues 16 filtered GET /events and one GET /verify; before
T7 each was a full-chain parse (17 parses of every line, measured 2.56 s of ledger CPU at 11.2k events, T6).
The cache keeps the last parse of each segment keyed by its exact BYTES (equal, or extended past a newline by
appends), so a pack parses each line once - and every read still returns exactly what a fresh store returns,
including after a same-size in-place edit, a rotation, a bad line or invalid UTF-8."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import sealed_ledger.store as store_mod
from field_core.ledger import LedgerEvent
from sealed_ledger.api import create_app
from sealed_ledger.store import LedgerStore

from ledger_c2_support import rotate

TYPES = ("gateway.request", "conformance.allow", "conformance.block", "delegation.mint",
         "governor.spend", "lifecycle.reattestation_due", "lifecycle.expiring_authority", "kill.agent")
N = 120


@pytest.fixture
def validations(monkeypatch):
    """Counts every LedgerEvent.model_validate call - one per parsed line."""
    calls = [0]
    original = LedgerEvent.model_validate

    def counting(obj, *args, **kwargs):
        calls[0] += 1
        return original(obj, *args, **kwargs)

    monkeypatch.setattr(LedgerEvent, "model_validate", counting)
    return calls


def _seed(tmp_path, n: int = N) -> LedgerStore:
    store = LedgerStore(tmp_path / "events.jsonl")
    for i in range(n):
        store.append(TYPES[i % len(TYPES)], {"seq": i, "token_id": f"tok-{i % 7}"}, f"agent-{i % 5}")
    return store


def _pack_reads(store: LedgerStore):
    out = [store.events(event_type=t) for t in TYPES]
    out += [store.events(agent_id=f"agent-{k}") for k in range(5)]
    out += [store.events(since="2000-01-01T00:00:00Z"), store.events(limit=10), store.events()]
    return out, store.verify()


def _dump(events) -> list[dict]:
    return [e.model_dump(mode="json") for e in events]


def _uncached_verify(store: LedgerStore):
    """The pre-T7 verification of the same bytes: a Snapshot built without the store's cached parser."""
    snap = store._take_snapshot(tolerant=True)
    return store_mod.Snapshot(snap.layout, snap.raw, 1, tolerant=True).verify()


def _same_as_fresh(store: LedgerStore) -> None:
    fresh = LedgerStore(store.path)
    assert _dump(store.events()) == _dump(fresh.events())
    assert store.verify() == fresh.verify()


def test_pack_shaped_reads_parse_each_line_once(tmp_path, validations):
    store = _seed(tmp_path)
    validations[0] = 0
    reads, verification = _pack_reads(store)
    assert verification.ok and verification.length == N
    assert len(reads) == 16 and len(reads[-1]) == N
    # main: 16 strict parses + 1 tolerant parse = 17 * N validations
    assert validations[0] == N, f"{validations[0]} line parses for 16 reads + 1 verify of {N} events"


def test_pack_shaped_http_reads_parse_each_line_once(tmp_path, validations):
    store = _seed(tmp_path)
    client = TestClient(create_app(store=store))
    validations[0] = 0
    for t in TYPES:
        assert client.get("/events", params={"event_type": t}).status_code == 200
    for k in range(5):
        assert client.get("/events", params={"agent_id": f"agent-{k}"}).status_code == 200
    assert client.get("/events", params={"since": "2000-01-01T00:00:00Z"}).status_code == 200
    assert len(client.get("/events").json()) == N
    assert client.get("/events", params={"limit": 10}).status_code == 200
    body = client.get("/verify").json()
    assert body["ok"] is True and body["length"] == N
    assert validations[0] == N


def test_an_append_parses_only_the_new_lines(tmp_path, validations):
    store = _seed(tmp_path)
    store.events()
    for i in range(3):
        store.append("gateway.request", {"seq": N + i}, "agent-0")
    validations[0] = 0
    assert len(store.events()) == N + 3
    assert validations[0] == 3
    verification = store.verify()
    assert verification.ok and verification.length == N + 3
    assert validations[0] == 3
    _same_as_fresh(store)


def test_unchanged_verify_is_reused_and_an_append_recomputes_it(tmp_path, validations, monkeypatch):
    store = _seed(tmp_path)
    chains = [0]
    original = store_mod.verify_chain

    def counting(events, *args, **kwargs):
        chains[0] += 1
        return original(events, *args, **kwargs)

    monkeypatch.setattr(store_mod, "verify_chain", counting)
    first = store.verify()
    validations[0], chains[0] = 0, 0
    again = store.verify()
    assert again == first and validations[0] == 0 and chains[0] == 0
    store.append("gateway.request", {"seq": N}, "agent-0")
    after = store.verify()
    assert after.ok and after.length == N + 1 and chains[0] == 1


def test_a_same_size_in_place_edit_is_seen(tmp_path):
    store = _seed(tmp_path)
    assert store.verify().ok and len(store.events()) == N  # warm both caches
    raw = store.path.read_bytes()
    lines = raw.split(b"\n")
    victim = json.loads(lines[N // 2])
    seq = victim["payload"]["seq"]
    old, new = str(seq).encode(), str(seq + 1 if len(str(seq + 1)) == len(str(seq)) else seq - 1).encode()
    assert len(old) == len(new) and old != new
    key = lines[N // 2].index(b'"seq":') + len(b'"seq":')
    key += len(lines[N // 2][key:]) - len(lines[N // 2][key:].lstrip())  # compact or spaced JSON
    assert lines[N // 2][key:key + len(old)] == old
    offset = sum(len(x) + 1 for x in lines[: N // 2]) + key
    inode = store.path.stat().st_ino
    with open(store.path, "r+b") as fh:  # same size, same inode
        fh.seek(offset)
        fh.write(new)
    assert store.path.stat().st_size == len(raw) and store.path.stat().st_ino == inode
    verification = store.verify()
    assert not verification.ok and verification.first_break_index == N // 2
    assert store.events()[N // 2].payload["seq"] == json.loads(new)
    _same_as_fresh(store)


def test_invalid_utf8_still_raises_for_a_strict_reader_after_a_verify(tmp_path):
    store = _seed(tmp_path)
    store.events()
    line = store.path.read_bytes().split(b"\n")[0].replace(b'"tok-0"', b'"tok-\xff"')
    with open(store.path, "ab") as fh:
        fh.write(line + b"\n")
    # (a fresh LedgerStore cannot even open these bytes: its constructor parses strictly, before and after T7)
    verification = store.verify()  # tolerant: replaced, then a break
    assert not verification.ok and verification == _uncached_verify(store)
    with pytest.raises(UnicodeDecodeError):
        store.events()  # strict: raises as before T7, although the tolerant parse just succeeded


def test_a_bad_line_is_reported_as_before_and_never_cached(tmp_path):
    store = _seed(tmp_path)
    store.events()
    with open(store.path, "ab") as fh:
        fh.write(b'{"not": "an event"}\n')
    verification = store.verify()
    assert not verification.ok and verification.first_break_index == N
    assert verification == _uncached_verify(store)
    with pytest.raises(ValueError):
        store.events()


def test_a_rewrite_that_is_not_an_extension_is_parsed_in_full(tmp_path, validations):
    store = _seed(tmp_path)
    store.events()
    lines = store.path.read_bytes().split(b"\n")
    store.path.write_bytes(b"\n".join(lines[: N // 2]) + b"\n")  # truncated: a prefix, not an extension
    validations[0] = 0
    assert len(store.events()) == N // 2
    assert validations[0] == N // 2
    _same_as_fresh(store)


def test_each_reader_gets_its_own_list(tmp_path):
    store = _seed(tmp_path)
    first = store.events()
    first.clear()
    assert len(store.events()) == N


def test_a_ledger_over_the_cap_parses_on_every_read_as_before(tmp_path, validations, monkeypatch):
    store = _seed(tmp_path)
    monkeypatch.setattr(store_mod, "PARSE_CACHE_MAX_BYTES", 100)
    validations[0] = 0
    a, b = store.events(), store.events()
    assert validations[0] == 2 * N and _dump(a) == _dump(b)
    store.verify()
    store.verify()
    assert validations[0] == 4 * N


def test_a_rotated_ledger_reads_and_verifies_as_a_fresh_store(tmp_path, validations):
    store = _seed(tmp_path)
    store.events()
    rotate(store)
    for i in range(4):
        store.append("gateway.request", {"seq": N + i}, "agent-1")
    _same_as_fresh(store)
    assert store.verify().ok
    validations[0] = 0
    store.events()
    store.verify()
    assert validations[0] == 0  # both segments' bytes unchanged since the last read
