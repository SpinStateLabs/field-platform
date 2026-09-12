"""v1.2 B4 — attestation, and the SQLite migration that makes it reachable.

Two properties are security-relevant and each has a test that fails if the
guard is weakened:

* a PATCH must not be able to set ``attested_at`` / ``attested_by`` (forging
  an attestation, or resetting the lifecycle staleness clock, with an
  ordinary record edit);
* an attestation signed by nobody (blank / whitespace) must be refused.

The migration test builds the OLD 8-column table by hand — the shape both
estate databases have on disk today — because ``CREATE TABLE IF NOT EXISTS``
would silently leave it that way.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.store import AgentNotFoundError, RegistryStore

OLD_SCHEMA = """
CREATE TABLE agents (
    agent_id     TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    owner        TEXT NOT NULL,
    domain       TEXT NOT NULL DEFAULT 'general',
    manifest_ref TEXT,
    status       TEXT NOT NULL DEFAULT 'active',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
"""


@pytest.fixture()
def client(tmp_path):
    store = RegistryStore(tmp_path / "agents.sqlite3")
    app = create_app(store=store)
    with TestClient(app) as c:
        c.post("/agents", json={"agent_id": "invoicing-agent", "name": "Invoicing",
                                "owner": "AP Team Lead", "domain": "finance"})
        yield c
    store.close()


def test_attest_records_who_and_when(client):
    r = client.post("/agents/invoicing-agent/attest",
                    json={"attested_by": "  Don Hagell  "})
    assert r.status_code == 200
    body = r.json()
    assert body["attested_by"] == "Don Hagell"   # stripped
    assert body["attested_at"] is not None
    assert client.get("/agents/invoicing-agent").json()["attested_by"] == "Don Hagell"


def test_adversarial_blank_attester_is_422(client):
    """An attestation nobody signed is worse than none: it moves the clock."""
    for blank in ("", "   ", "\t\n"):
        r = client.post("/agents/invoicing-agent/attest",
                        json={"attested_by": blank})
        assert r.status_code == 422, blank
    assert client.get("/agents/invoicing-agent").json()["attested_at"] is None


def test_attest_unknown_agent_is_404(client):
    r = client.post("/agents/ghost-agent/attest", json={"attested_by": "Don"})
    assert r.status_code == 404


def test_adversarial_patch_cannot_forge_attestation(client):
    """`extra='forbid'` on AgentUpdate is the guard. If someone adds these
    fields to AgentUpdate, this test fails — which is the point."""
    for payload in (
        {"attested_by": "Impostor"},
        {"attested_at": "2020-01-01T00:00:00+00:00"},
        {"attested_by": "Impostor", "attested_at": "2020-01-01T00:00:00+00:00"},
    ):
        r = client.patch("/agents/invoicing-agent", json=payload)
        assert r.status_code == 422, payload
    record = client.get("/agents/invoicing-agent").json()
    assert record["attested_by"] is None and record["attested_at"] is None


def test_patch_does_not_reset_the_reattestation_clock(client):
    """A kill/revive cycle (two PATCHes) must not look like an attestation."""
    client.post("/agents/invoicing-agent/attest", json={"attested_by": "Don"})
    attested_at = client.get("/agents/invoicing-agent").json()["attested_at"]

    client.patch("/agents/invoicing-agent", json={"status": "killed"})
    client.patch("/agents/invoicing-agent", json={"status": "active"})
    client.patch("/agents/invoicing-agent", json={"owner": "Someone Else"})

    after = client.get("/agents/invoicing-agent").json()
    assert after["attested_at"] == attested_at
    assert after["attested_by"] == "Don"
    assert after["updated_at"] != attested_at  # updated_at DID move — the point


def test_attest_writes_a_ledger_event(tmp_path):
    events: list[tuple] = []

    class SpyLedger:
        def append(self, event_type, payload, agent_id):
            events.append((event_type, payload, agent_id))

    store = RegistryStore(tmp_path / "a.sqlite3")
    c = TestClient(create_app(store=store, ledger=SpyLedger()))
    c.post("/agents", json={"agent_id": "a1", "name": "A", "owner": "O"})
    c.post("/agents/a1/attest", json={"attested_by": "Don"})
    assert ("registry.attested", "a1") in [(e[0], e[2]) for e in events]
    attested = [e for e in events if e[0] == "registry.attested"][0]
    assert attested[1]["attested_by"] == "Don"
    store.close()


def test_store_migrates_an_old_eight_column_database(tmp_path):
    """The estate databases are persisted files: CREATE TABLE IF NOT EXISTS
    never adds a column to them. Build the old shape, with a row in it, and
    prove the store both reads that row and adds the columns."""
    path = tmp_path / "old.sqlite3"
    raw = sqlite3.connect(str(path))
    raw.executescript(OLD_SCHEMA)
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat()
    raw.execute(
        "INSERT INTO agents VALUES (?,?,?,?,?,?,?,?)",
        ("legacy-agent", "Legacy", "Owner", "finance", "/data/manifests/x.yaml",
         "active", stamp, stamp),
    )
    raw.commit()
    cols_before = {r[1] for r in raw.execute("PRAGMA table_info(agents)")}
    raw.close()
    assert "attested_at" not in cols_before and len(cols_before) == 8

    store = RegistryStore(path)
    try:
        record = store.get("legacy-agent")           # the pre-existing row reads
        assert record.owner == "Owner"
        assert record.attested_at is None and record.attested_by is None
        assert [r.agent_id for r in store.list()] == ["legacy-agent"]

        check = sqlite3.connect(str(path))
        cols_after = {r[1] for r in check.execute("PRAGMA table_info(agents)")}
        check.close()
        assert {"attested_at", "attested_by"} <= cols_after

        # and the migrated database still takes new rows (named-column INSERT)
        from agent_registry.models import AgentCreate

        store.add(AgentCreate(agent_id="new-agent", name="New", owner="Owner"))
        assert store.attest("legacy-agent", "Don").attested_by == "Don"
        assert store.get("legacy-agent").attested_by == "Don"
    finally:
        store.close()


def test_migration_is_idempotent_across_reopens(tmp_path):
    path = tmp_path / "a.sqlite3"
    s1 = RegistryStore(path)
    from agent_registry.models import AgentCreate

    s1.add(AgentCreate(agent_id="a1", name="A", owner="O"))
    s1.attest("a1", "Don")
    s1.close()
    s2 = RegistryStore(path)          # second open must not raise
    try:
        assert s2.get("a1").attested_by == "Don"
    finally:
        s2.close()


def test_attest_on_unknown_agent_raises_at_the_store(tmp_path):
    store = RegistryStore(tmp_path / "a.sqlite3")
    try:
        with pytest.raises(AgentNotFoundError):
            store.attest("nobody", "Don")
    finally:
        store.close()
