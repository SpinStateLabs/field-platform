"""RegistryStore.update and attest are atomic read-modify-write steps.

v1.2 hardening, OPEN-A. ``update`` read the record, released the lock, then
wrote EVERY column back from that read. kill-switch kills through
``PATCH /agents/{id}``, so a concurrent PATCH of ``manifest_ref`` wrote the
stale ``status`` back: the kill returned 200 ``killed`` and the agent ended
``active``. The API's status-change ledger note compared a separate, earlier
``get``, so the same race ledgered status changes a PATCH never made, and
``attest`` returned a copy of a read that a concurrent write had made stale.

Each race is released by a barrier and repeated over ``TRIALS`` trials.
Bounded: fixed thread and trial counts, and a join timeout that turns a
deadlock into a failure.
"""

from __future__ import annotations

import sqlite3
import threading

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent_registry.api import create_app
from agent_registry.models import AgentCreate, AgentRecord, AgentStatus, AgentUpdate
from agent_registry.store import RegistryStore

TRIALS = 25
EDITORS = 6  # concurrent manifest_ref edits racing each kill
JOIN_TIMEOUT_S = 60

COLUMNS = ("agent_id", "name", "owner", "domain", "manifest_ref", "status",
           "created_at", "updated_at", "attested_at", "attested_by")


class _Stores:
    """Opens stores on one file; teardown closes them unless a racing call
    deadlocked (a hung thread may still hold the lock ``close`` needs)."""

    def __init__(self, path):
        self.path = path
        self.opened: list[RegistryStore] = []
        self.deadlocked = False

    def open(self) -> RegistryStore:
        store = RegistryStore(self.path)
        self.opened.append(store)
        return store


@pytest.fixture()
def stores(tmp_path):
    box = _Stores(tmp_path / "agents.sqlite3")
    yield box
    if not box.deadlocked:
        for store in box.opened:
            store.close()


def _race(stores: _Stores, calls) -> list[str]:
    """Run each call on its own thread, released together by a barrier.
    Returns the exceptions raised, as strings."""
    barrier = threading.Barrier(len(calls))
    errors: list[str] = []

    def run(call):
        try:
            barrier.wait()
            call()
        except Exception as exc:  # every exception is a failure here
            errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=run, args=(c,), daemon=True) for c in calls]
    for t in threads:
        t.start()
    for t in threads:
        t.join(JOIN_TIMEOUT_S)
    hung = sum(t.is_alive() for t in threads)
    if hung:
        stores.deadlocked = True
    assert not hung, f"{hung} racing call(s) still running after {JOIN_TIMEOUT_S} s: deadlock"
    return errors


def _add(store: RegistryStore, agent_id: str) -> None:
    store.add(AgentCreate(agent_id=agent_id, name=f"name-{agent_id}", owner="owner"))


def _kill_raced_by_edits(stores, killer, editor):
    lost, errors = [], []
    kill_reverted = edits_reverted = 0
    for t in range(TRIALS):
        aid = f"agent-{t}"
        _add(killer, aid)
        kill_returned: list[AgentRecord] = []
        calls = [lambda aid=aid: kill_returned.append(
            killer.set_status(aid, AgentStatus.KILLED))]
        calls += [lambda aid=aid, k=k: editor.update(
            aid, AgentUpdate(manifest_ref=f"ref-{k}")) for k in range(EDITORS)]
        errors += _race(stores, calls)
        final = killer.get(aid)
        kill_reverted += final.status is not AgentStatus.KILLED
        edits_reverted += final.manifest_ref is None
        if (final.status is not AgentStatus.KILLED
                or final.manifest_ref is None
                or [r.status for r in kill_returned] != [AgentStatus.KILLED]):
            lost.append(f"{aid}: final status={final.status.value} "
                        f"manifest_ref={final.manifest_ref} kill returned "
                        f"{[r.status.value for r in kill_returned]}")
    assert not errors, errors[:5]
    assert not lost, (
        f"{len(lost)} of {TRIALS} trials lost an update (final status not "
        f"killed: {kill_reverted}; every edit reverted: {edits_reverted}): {lost[:5]}"
    )


def test_patch_of_another_field_never_reverts_a_concurrent_kill(stores):
    """The OPEN-A race at the store: 1 kill + EDITORS manifest_ref edits.
    The kill must stick, and so must at least one edit."""
    store = stores.open()
    _kill_raced_by_edits(stores, killer=store, editor=store)


def test_edit_through_a_second_connection_never_reverts_a_kill(stores):
    """Same race with the edits on a second connection to the file (the
    ``registry`` CLI is a second process). A lock alone cannot cover this:
    only writing just the patched columns does."""
    _kill_raced_by_edits(stores, killer=stores.open(), editor=stores.open())


def _as_row(record: AgentRecord) -> tuple:
    dumped = record.model_dump()
    return tuple(
        dumped[c].isoformat() if hasattr(dumped[c], "isoformat")
        else getattr(dumped[c], "value", dumped[c])
        for c in COLUMNS
    )


def test_update_and_attest_return_the_row_their_own_write_produced(stores):
    """Every record ``set_status``/``update``/``attest`` returns must be a
    state the row really had (a trigger records every one) and must carry
    the call's own write. The pre-fix store returned a copy of its earlier
    read plus the patch: a row that never existed once a concurrent write
    landed in between."""
    store = stores.open()
    side = sqlite3.connect(stores.path)
    try:
        cols = ", ".join(COLUMNS)
        new = ", ".join(f"NEW.{c}" for c in COLUMNS)
        side.executescript(
            f"CREATE TABLE row_history ({cols});"
            f"CREATE TRIGGER hist_insert AFTER INSERT ON agents BEGIN "
            f"INSERT INTO row_history VALUES ({new}); END;"
            f"CREATE TRIGGER hist_update AFTER UPDATE ON agents BEGIN "
            f"INSERT INTO row_history VALUES ({new}); END;"
        )
        returned: list[tuple[str, str, AgentRecord]] = []
        guard = threading.Lock()

        def keep(call: str, record: AgentRecord) -> None:
            with guard:
                returned.append((call, record.agent_id, record))

        errors: list[str] = []
        for t in range(TRIALS):
            aid = f"agent-{t}"
            _add(store, aid)
            calls = [lambda aid=aid: keep(
                "set_status:killed", store.set_status(aid, AgentStatus.KILLED))]
            calls += [lambda aid=aid, k=k: keep(
                f"update:ref-{k}", store.update(aid, AgentUpdate(manifest_ref=f"ref-{k}")))
                for k in range(3)]
            calls += [lambda aid=aid, k=k: keep(
                f"attest:att-{k}", store.attest(aid, f"att-{k}"))
                for k in range(3)]
            errors += _race(stores, calls)

        history = set(side.execute(f"SELECT {cols} FROM row_history").fetchall())
    finally:
        side.close()

    wrong = []
    for call, aid, record in returned:
        kind, own = call.split(":")
        carried = {"set_status": record.status.value, "update": record.manifest_ref,
                   "attest": record.attested_by}[kind]
        if _as_row(record) not in history:
            wrong.append(f"{call} on {aid} returned a row that never existed")
        elif carried != own:
            wrong.append(f"{call} on {aid} returned another call's write ({carried})")
    assert not errors, errors[:5]
    assert len(returned) == TRIALS * 7
    assert not wrong, f"{len(wrong)} of {len(returned)} returned records: {wrong[:5]}"


def test_concurrent_kills_over_two_connections_report_exactly_one_change(stores):
    """``update_with_previous`` reads its pre-image inside the write
    transaction, so of 4 concurrent kills over 2 connections exactly one sees
    active -> killed -- the before/after pair the API ledgers from."""
    first, second = stores.open(), stores.open()
    wrong, errors = [], []
    for t in range(TRIALS):
        aid = f"agent-{t}"
        _add(first, aid)
        pairs: list[tuple[AgentStatus, AgentStatus]] = []
        guard = threading.Lock()

        def kill(store, aid=aid):
            before, after = store.update_with_previous(
                aid, AgentUpdate(status=AgentStatus.KILLED))
            with guard:
                pairs.append((before.status, after.status))

        errors += _race(stores, [lambda s=s: kill(s) for s in (first, first, second, second)])
        changes = [p for p in pairs if p[0] is not p[1]]
        if (changes != [(AgentStatus.ACTIVE, AgentStatus.KILLED)]
                or any(after is not AgentStatus.KILLED for _, after in pairs)):
            wrong.append(f"{aid}: {[(b.value, a.value) for b, a in pairs]}")
    assert not errors, errors[:5]
    assert not wrong, f"{len(wrong)} of {TRIALS} trials: {wrong[:5]}"


class _RecordingLedger:
    def __init__(self):
        self._lock = threading.Lock()
        self.events: list[tuple[str, str, dict]] = []

    def append(self, event_type, payload=None, agent_id=None):
        with self._lock:
            self.events.append((agent_id, event_type, payload))


def test_api_kill_raced_by_edits_sticks_and_ledgers_one_status_change(stores):
    """The OPEN-A repro through the real app: PATCH status=killed raced by
    EDITORS PATCH manifest_ref on the same agent. Every trial must end
    ``killed`` with exactly one ``registry.status_changed`` (active ->
    killed) and one ``registry.updated`` per edit. Reading ``before`` with a
    separate ``get`` ledgered edits as status changes."""
    ledger = _RecordingLedger()
    app = create_app(store=stores.open(), ledger=ledger)
    clients = [TestClient(app) for _ in range(EDITORS + 1)]
    wrong, errors = [], []
    for t in range(TRIALS):
        aid = f"agent-{t}"
        created = clients[0].post("/agents", json={"agent_id": aid, "name": "n", "owner": "o"})
        assert created.status_code == 201, created.text
        codes: list[int] = []
        calls = [lambda aid=aid: codes.append(
            clients[0].patch(f"/agents/{aid}", json={"status": "killed"}).status_code)]
        calls += [lambda aid=aid, k=k: codes.append(
            clients[k].patch(f"/agents/{aid}", json={"manifest_ref": f"ref-{k}"}).status_code)
            for k in range(1, EDITORS + 1)]
        errors += _race(stores, calls)
        final = clients[0].get(f"/agents/{aid}").json()["status"]
        notes = [(e, p) for a, e, p in ledger.events if a == aid]
        status_notes = [p for e, p in notes if e == "registry.status_changed"]
        updated_notes = [p for e, p in notes if e == "registry.updated"]
        if (final != "killed" or codes != [200] * (EDITORS + 1)
                or status_notes != [{"from": "active", "to": "killed"}]
                or updated_notes != [{"fields": ["manifest_ref"]}] * EDITORS):
            wrong.append(f"{aid}: final={final} codes={sorted(codes)} "
                         f"status_changed={status_notes} updated={len(updated_notes)}")
    assert not errors, errors[:5]
    assert not wrong, f"{len(wrong)} of {TRIALS} trials: {wrong[:5]}"


def test_a_patch_whose_result_cannot_be_read_back_is_rolled_back(stores):
    """``update`` converts its read-back before COMMIT. ``AgentUpdate``
    accepted ``name=""``, which ``AgentRecord`` rejects; the pre-fix store
    persisted it, after which every ``get``/``list`` of the registry raised.
    Now the call raises and nothing is written.

    ``AgentUpdate`` now rejects ``name=""`` itself (min_length=1, see
    test_registry_update_validation.py), so the patch is built with
    ``model_construct`` to skip that check: a plain ``AgentUpdate(name="")``
    would raise ValidationError before the store is ever called, and this
    test would pass without exercising the store's roll-back at all."""
    store = stores.open()
    _add(store, "agent-0")
    before = store.get("agent-0")
    with pytest.raises(ValidationError):
        store.update("agent-0", AgentUpdate.model_construct(name=""))
    assert store.get("agent-0") == before
    assert store.list() == [before]
