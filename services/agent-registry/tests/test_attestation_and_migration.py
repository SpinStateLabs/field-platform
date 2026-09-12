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


# --- guards that were correct but unpinned (Phase B review) -------------------


def test_adversarial_attest_body_cannot_smuggle_a_backdated_timestamp(client):
    """`AttestRequest` is `extra='forbid'` so a caller cannot post
    `attested_at` and choose when the staleness clock restarts.

    Without this the only other test of `extra='forbid'` is on the PATCH
    route, so flipping THIS model to `extra='allow'` left the whole suite
    green — and `attested_at` is the one field that clears a
    `lifecycle.reattestation_due` escalation."""
    r = client.post("/agents/invoicing-agent/attest", json={
        "attested_by": "Don Hagell",
        "attested_at": "2020-01-01T00:00:00Z",
    })
    assert r.status_code == 422, r.text
    assert any(d["type"] == "extra_forbidden" for d in r.json()["detail"])
    assert client.get("/agents/invoicing-agent").json()["attested_at"] is None


def test_adversarial_attest_body_rejects_any_unknown_key(client):
    r = client.post("/agents/invoicing-agent/attest",
                    json={"attested_by": "Don Hagell", "status": "active"})
    assert r.status_code == 422, r.text


def test_the_cli_attest_ledgers_the_event_it_writes(tmp_path, monkeypatch):
    """`registry attest` writes SQLite directly, so it has to append
    `registry.attested` itself or the audit trail has a hole exactly where it
    matters: `attested_at` is the only field that clears a
    `lifecycle.reattestation_due` escalation."""
    from sealed_ledger.api import create_app as create_ledger_app
    from sealed_ledger.store import LedgerStore
    import field_core.clients as fc
    from agent_registry import cli

    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "e.jsonl")))
    monkeypatch.setenv("FIELD_LEDGER_URL", "http://ledger.test")

    class Recording:
        def __init__(self):
            self.calls = []

        def append(self, event_type, payload=None, agent_id=None):
            self.calls.append((event_type, payload, agent_id))
            return ledger.post("/events", json={
                "event_type": event_type, "payload": payload or {},
                "agent_id": agent_id,
            })

    spy = Recording()
    monkeypatch.setattr(fc, "LedgerClient", lambda *a, **k: spy)

    db = tmp_path / "agents.sqlite3"
    store = RegistryStore(db)
    app = create_app(store=store)
    with TestClient(app) as c:
        c.post("/agents", json={"agent_id": "invoicing-agent", "name": "Invoicing",
                                "owner": "AP Team Lead", "domain": "finance"})
    store.close()
    spy.calls.clear()          # drop registry.registered from the setup above

    from typer.testing import CliRunner

    result = CliRunner().invoke(
        cli.app, ["attest", "invoicing-agent", "--by", "Don Hagell",
                  "--path", str(db)],
    )
    assert result.exit_code == 0, result.output
    assert [c[0] for c in spy.calls] == ["registry.attested"]
    assert spy.calls[0][2] == "invoicing-agent"
    assert spy.calls[0][1]["attested_by"] == "Don Hagell"
    assert spy.calls[0][1]["via"] == "cli"
    assert "ledgered: registry.attested" in result.output


def test_the_cli_attest_says_so_loudly_when_no_ledger_is_configured(
    tmp_path, monkeypatch
):
    """Silence is the failure mode that matters here: a compliance flag
    cleared with no audit record and no word to the operator."""
    from agent_registry import cli
    from typer.testing import CliRunner

    monkeypatch.delenv("FIELD_LEDGER_URL", raising=False)
    db = tmp_path / "agents.sqlite3"
    store = RegistryStore(db)
    app = create_app(store=store)
    with TestClient(app) as c:
        c.post("/agents", json={"agent_id": "invoicing-agent", "name": "Invoicing",
                                "owner": "AP Team Lead", "domain": "finance"})
    store.close()

    result = CliRunner().invoke(
        cli.app, ["attest", "invoicing-agent", "--by", "Don Hagell",
                  "--path", str(db)],
    )
    assert result.exit_code == 0, result.output
    assert "NOT on the ledger" in result.output


def test_the_cli_attest_exits_3_when_a_configured_ledger_refuses(
    tmp_path, monkeypatch
):
    """Attested but unledgered is not success. Exit 3 so a scripted run
    cannot treat a silent audit gap as a clean attestation."""
    import field_core.clients as fc
    from agent_registry import cli
    from typer.testing import CliRunner

    monkeypatch.setenv("FIELD_LEDGER_URL", "http://ledger.test")

    class Refusing:
        def append(self, *a, **k):
            raise RuntimeError("ledger unreachable")

    monkeypatch.setattr(fc, "LedgerClient", lambda *a, **k: Refusing())

    db = tmp_path / "agents.sqlite3"
    store = RegistryStore(db)
    app = create_app(store=store)
    with TestClient(app) as c:
        c.post("/agents", json={"agent_id": "invoicing-agent", "name": "Invoicing",
                                "owner": "AP Team Lead", "domain": "finance"})
    store.close()

    result = CliRunner().invoke(
        cli.app, ["attest", "invoicing-agent", "--by", "Don Hagell",
                  "--path", str(db)],
    )
    assert result.exit_code == 3, result.output
    assert "ledger refused" in result.output
    # the attestation itself still happened — the operator must know both
    store = RegistryStore(db)
    assert store.get("invoicing-agent").attested_by == "Don Hagell"
    store.close()
