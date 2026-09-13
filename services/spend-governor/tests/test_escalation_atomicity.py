"""Escalation open/resolve races, driven through the real FastAPI app.

1. Open. ``POST /spend`` and ``POST /usage`` used to call
   ``has_open_escalation()`` and then ``add_escalation()`` in two separate
   lock holds. Spends crossing the threshold together each saw "none open",
   so one crossing opened (and ledgered) up to 7 escalations of the same kind
   for the same agent. Now one store call checks and inserts in one hold and
   one ``BEGIN IMMEDIATE`` transaction, and a partial unique index makes "one
   open escalation per (agent, kind)" a schema invariant wherever the
   database has no legacy duplicates.

2. Resolve. ``UPDATE ... WHERE escalation_id=?`` let every later resolver
   overwrite ``resolved_by``. Now the first resolver wins: one 200 and one
   ``spend.escalation_resolved`` note; the same human retrying gets 200 and
   the unchanged row; anyone else gets 409 and the unchanged row.

3. Migration. A persisted database may already hold duplicate open rows. The
   store must still open (the duplicates stay in the human queue; nothing is
   auto-resolved) and must add the index on a later open once they are gone.

Bounded: fixed trial and thread counts; ONE 60 s join budget per race.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from spend_governor.api import create_app
from spend_governor.core import Escalation, GovernorStore

THREADS = 8
TRIALS = 20
JOIN_BUDGET_S = 60


class RecordingLedger:
    def __init__(self) -> None:
        self.notes: list[tuple[str, dict, str]] = []
        self._guard = threading.Lock()

    def append(self, event_type, payload=None, agent_id=None):
        with self._guard:
            self.notes.append((event_type, payload or {}, agent_id))

    def of(self, event_type: str, agent_id: str) -> list[dict]:
        with self._guard:
            return [p for t, p, a in self.notes if t == event_type and a == agent_id]


def _race(fns) -> int:
    """Release every fn together; return how many threads are still running
    when ONE shared budget runs out (a deadlock fails fast)."""
    barrier = threading.Barrier(len(fns))

    def run(fn):
        barrier.wait()
        fn()

    pool = [threading.Thread(target=run, args=(fn,), daemon=True) for fn in fns]
    for t in pool:
        t.start()
    deadline = time.monotonic() + JOIN_BUDGET_S
    for t in pool:
        t.join(timeout=max(0.0, deadline - time.monotonic()))
    return sum(t.is_alive() for t in pool)


@pytest.fixture()
def api(tmp_path):
    store = GovernorStore(tmp_path / "spend.sqlite3")
    ledger = RecordingLedger()
    app = create_app(store=store, ledger=ledger)
    clients = [TestClient(app) for _ in range(THREADS)]
    yield store, ledger, clients
    store.close()


def _cap(client, agent, limit_cents=10_000):
    r = client.put(f"/caps/{agent}", json={
        "agent_id": agent, "limit_cents": limit_cents, "period": "total",
        "escalate_at_pct": 80})
    assert r.status_code == 200, r.text


def test_concurrent_spends_crossing_the_threshold_open_one_escalation(api):
    store, ledger, clients = api
    bad: list[str] = []
    for trial in range(TRIALS):
        agent = f"agent-{trial}"
        _cap(clients[0], agent)  # escalate at 8_000 of 10_000
        # 7_998 spent: EVERY one of the racing 2-cent spends crosses by itself
        r = clients[0].post("/spend", json={"agent_id": agent, "cents": 7_998})
        assert r.status_code == 201 and r.json()["state"] == "OK", r.text
        responses: list = []

        def spend(k):
            return lambda: responses.append(
                clients[k].post("/spend", json={"agent_id": agent, "cents": 2}))

        assert _race([spend(k) for k in range(THREADS)]) == 0, "deadlock"
        codes = Counter((x.status_code, x.json().get("state")) for x in responses)
        opened = [e for e in clients[0].get("/escalations", params={"agent_id": agent}).json()
                  if e["kind"] == "cents"]
        notes = ledger.of("spend.escalate", agent)
        if codes != Counter({(201, "ESCALATE"): THREADS}):
            bad.append(f"{agent}: responses {dict(codes)}")
        elif len(opened) != 1 or len(notes) != 1:
            bad.append(f"{agent}: {len(opened)} open cents escalations, "
                       f"{len(notes)} spend.escalate notes")
        elif notes[0]["escalation_id"] != opened[0]["escalation_id"]:
            bad.append(f"{agent}: note names {notes[0]['escalation_id']}, "
                       f"open is {opened[0]['escalation_id']}")
    assert not bad, f"{len(bad)} of {TRIALS} trials: {bad[:5]}"


def test_concurrent_rogue_usage_opens_one_escalation_per_kind(api):
    store, ledger, clients = api
    bad: list[str] = []
    for trial in range(TRIALS // 2):
        agent = f"rogue-{trial}"
        _cap(clients[0], agent, limit_cents=10_000_000)
        r = clients[0].put(f"/policies/{agent}", json={
            "agent_id": agent, "allowed_models": ["claude-haiku-4-5"]})
        assert r.status_code == 200, r.text
        responses: list = []

        def use(k):
            return lambda: responses.append(clients[k].post("/usage", json={
                "agent_id": agent, "model": "claude-opus-4-8",
                "input_tokens": 10, "output_tokens": 10}))

        assert _race([use(k) for k in range(THREADS)]) == 0, "deadlock"
        if sorted(x.status_code for x in responses) != [201] * THREADS:
            bad.append(f"{agent}: {[x.status_code for x in responses]}")
            continue
        opened = [e for e in clients[0].get("/escalations", params={"agent_id": agent}).json()
                  if e["kind"] == "usage:rogue_model"]
        notes = ledger.of("usage.rogue_model", agent)
        if len(opened) != 1 or len(notes) != 1:
            bad.append(f"{agent}: {len(opened)} open usage:rogue_model escalations, "
                       f"{len(notes)} usage.rogue_model notes")
    assert not bad, f"{len(bad)} of {TRIALS // 2} trials: {bad[:5]}"


def _open_one(client, agent) -> str:
    _cap(client, agent, limit_cents=100)
    assert client.post("/spend", json={"agent_id": agent, "cents": 90}).status_code == 201
    (esc,) = client.get("/escalations", params={"agent_id": agent}).json()
    return esc["escalation_id"]


def test_concurrent_resolves_the_first_resolver_wins(api):
    store, ledger, clients = api
    bad: list[str] = []
    for trial in range(TRIALS // 2):
        agent = f"agent-{trial}"
        esc_id = _open_one(clients[0], agent)
        results: dict[int, tuple[int, dict]] = {}

        def resolve(k):
            def call():
                r = clients[k].post(f"/escalations/{esc_id}/resolve",
                                    json={"resolved_by": f"human-{k}"})
                results[k] = (r.status_code, r.json())
            return call

        assert _race([resolve(k) for k in range(THREADS)]) == 0, "deadlock"
        winners = [k for k, (code, _) in results.items() if code == 200]
        codes = sorted(code for code, _ in results.values())
        if len(winners) != 1 or codes != [200] + [409] * (THREADS - 1):
            bad.append(f"{agent}: codes {codes}")
            continue
        winner = f"human-{winners[0]}"
        row = results[winners[0]][1]
        if row["resolved_by"] != winner or not row["resolved"]:
            bad.append(f"{agent}: 200 body {row} is not {winner}'s resolution")
        if any(body != row for _, body in results.values()):
            bad.append(f"{agent}: a 409 body differs from the winner's row")
        notes = ledger.of("spend.escalation_resolved", agent)
        if [n["resolved_by"] for n in notes] != [winner]:
            bad.append(f"{agent}: resolved notes {notes}")
        # afterwards: the winner retrying is idempotent, anyone else is refused
        again = clients[0].post(f"/escalations/{esc_id}/resolve", json={"resolved_by": winner})
        late = clients[0].post(f"/escalations/{esc_id}/resolve", json={"resolved_by": "late"})
        if (again.status_code, again.json()) != (200, row):
            bad.append(f"{agent}: winner retry gave {again.status_code} {again.json()}")
        if (late.status_code, late.json()) != (409, row):
            bad.append(f"{agent}: late resolver gave {late.status_code} {late.json()}")
        if len(ledger.of("spend.escalation_resolved", agent)) != 1:
            bad.append(f"{agent}: a retry or a refused resolve wrote a resolved note")
    assert not bad, f"{len(bad)} problems: {bad[:5]}"


def test_resolve_sequence_404_200_idempotent_409(api):
    store, ledger, clients = api
    client = clients[0]
    assert client.post("/escalations/nope/resolve",
                       json={"resolved_by": "alice"}).status_code == 404
    esc_id = _open_one(client, "a1")
    first = client.post(f"/escalations/{esc_id}/resolve", json={"resolved_by": "alice"})
    assert first.status_code == 200
    assert (first.json()["resolved"], first.json()["resolved_by"]) == (True, "alice")
    retry = client.post(f"/escalations/{esc_id}/resolve", json={"resolved_by": "alice"})
    assert (retry.status_code, retry.json()) == (200, first.json())
    other = client.post(f"/escalations/{esc_id}/resolve", json={"resolved_by": "bob"})
    assert (other.status_code, other.json()) == (409, first.json())
    assert client.get("/escalations", params={"agent_id": "a1"}).json() == []
    assert [n["resolved_by"] for n in ledger.of("spend.escalation_resolved", "a1")] == ["alice"]
    # the store keeps alice too, through both public methods
    assert store.resolve_escalation(esc_id, "carol").resolved_by == "alice"
    assert store.resolve_escalation_once(esc_id, "carol")[1] is False


# Shape of a persisted database written before the unique index existed.
_LEGACY_ESCALATIONS = """
CREATE TABLE escalations (
    escalation_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, ts TEXT NOT NULL,
    kind TEXT NOT NULL, spent INTEGER NOT NULL, "limit" INTEGER NOT NULL,
    pct INTEGER NOT NULL, resolved INTEGER NOT NULL DEFAULT 0, resolved_by TEXT
);
"""


def _index_present(path) -> bool:
    conn = sqlite3.connect(str(path))
    try:
        return conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name='uq_escalations_open'"
        ).fetchone() is not None
    finally:
        conn.close()


def test_store_opens_a_database_that_already_holds_duplicate_open_escalations(
    tmp_path, caplog
):
    path = tmp_path / "spend.sqlite3"
    conn = sqlite3.connect(str(path))
    with conn:
        conn.executescript(_LEGACY_ESCALATIONS)
        rows = [
            ("dup-1", "a", "2026-09-01T00:00:01+00:00", "cents", 80, 100, 80, 0, None),
            ("dup-2", "a", "2026-09-01T00:00:02+00:00", "cents", 81, 100, 80, 0, None),
            ("dup-3", "b", "2026-09-01T00:00:03+00:00", "usage:rogue_model", 1, 0, 80, 0, None),
            ("dup-4", "b", "2026-09-01T00:00:04+00:00", "usage:rogue_model", 1, 0, 80, 0, None),
            ("dup-5", "b", "2026-09-01T00:00:05+00:00", "usage:rogue_model", 1, 0, 80, 0, None),
            ("old-1", "a", "2026-08-01T00:00:00+00:00", "cents", 80, 100, 80, 1, "setup"),
        ]
        conn.executemany("INSERT INTO escalations VALUES (?,?,?,?,?,?,?,?,?)", rows)
    conn.close()

    with caplog.at_level(logging.WARNING, logger="spend_governor.core"):
        store = GovernorStore(path)  # must not raise
    try:
        assert store.open_escalation_index is False
        assert not _index_present(path)
        assert "2 (agent, kind) pair(s)" in caplog.text
        # nothing auto-resolved: the humans still see every duplicate
        assert [e.escalation_id for e in store.open_escalations("a")] == ["dup-1", "dup-2"]
        assert len(store.open_escalations("b")) == 3

        # the API still opens no further duplicate and ledgers nothing new
        ledger = RecordingLedger()
        client = TestClient(create_app(store=store, ledger=ledger))
        _cap(client, "a", limit_cents=100)
        r = client.post("/spend", json={"agent_id": "a", "cents": 95})
        assert r.status_code == 201 and r.json()["state"] == "ESCALATE", r.text
        assert len(store.open_escalations("a")) == 2
        assert ledger.of("spend.escalate", "a") == []
        esc, created = store.add_escalation_if_none_open(Escalation(
            escalation_id="new", agent_id="a", ts="2026-09-13T00:00:00+00:00",
            kind="cents", spent=95, limit=100, pct=80))
        assert (esc.escalation_id, created) == ("dup-1", False)  # the oldest open

        # humans clear the duplicates; the next open adds the index
        for esc_id in ("dup-2", "dup-4", "dup-5"):
            assert client.post(f"/escalations/{esc_id}/resolve",
                               json={"resolved_by": "ops"}).status_code == 200
    finally:
        store.close()

    reopened = GovernorStore(path)
    try:
        assert reopened.open_escalation_index is True
        assert _index_present(path)
        with pytest.raises(sqlite3.IntegrityError):
            reopened.add_escalation(Escalation(
                escalation_id="dup-6", agent_id="a", ts="2026-09-13T00:00:00+00:00",
                kind="cents", spent=1, limit=100, pct=80))
        reopened.add_escalation(Escalation(  # a RESOLVED duplicate is fine
            escalation_id="old-2", agent_id="a", ts="2026-09-13T00:00:00+00:00",
            kind="cents", spent=1, limit=100, pct=80, resolved=True, resolved_by="x"))
    finally:
        reopened.close()


def test_two_connections_opening_the_same_escalation_create_one(tmp_path):
    path = tmp_path / "spend.sqlite3"
    stores = [GovernorStore(path), GovernorStore(path)]
    try:
        assert all(s.open_escalation_index for s in stores)
        bad: list[str] = []
        for trial in range(TRIALS // 2):
            created: list[bool] = []
            errors: list[str] = []

            def open_via(k):
                def call():
                    try:
                        _, made = stores[k % 2].add_escalation_if_none_open(Escalation(
                            escalation_id=f"t{trial}-k{k}", agent_id=f"agent-{trial}",
                            ts=f"2026-09-13T00:00:{k:02d}+00:00", kind="cents",
                            spent=k, limit=100, pct=80))
                        created.append(made)
                    except Exception as exc:  # noqa: BLE001 - every error is a failure
                        errors.append(f"{type(exc).__name__}: {exc}")
                return call

            assert _race([open_via(k) for k in range(THREADS)]) == 0, "deadlock"
            if errors or created.count(True) != 1 or len(stores[0].open_escalations(f"agent-{trial}")) != 1:
                bad.append(f"trial {trial}: created={created} errors={errors[:2]}")
        assert not bad, bad[:5]
    finally:
        for s in stores:
            s.close()
