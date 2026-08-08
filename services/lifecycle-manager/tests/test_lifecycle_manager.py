"""lifecycle-manager tests: findings, ledger events, auto-kill discipline."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from lifecycle_manager.engine import LifecycleEngine, SweepConfig, render_markdown
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

NOW = datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)

ROSTER = "owner,department\nAP Team Lead,finance\nController Spin State,finance\n"


@pytest.fixture()
def stack(tmp_path):
    registry = TestClient(
        create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3"))
    )
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    delegation = TestClient(
        create_delegation_app(
            store=TokenStore(tmp_path / "tokens.sqlite3"),
            ledger=LedgerClient(client=ledger, base_url="http://t"),
            registry=RegistryClient(client=registry, base_url="http://t"),
        )
    )
    killswitch = TestClient(
        create_kill_app(
            registry=RegistryClient(client=registry, base_url="http://t"),
            ledger=LedgerClient(client=ledger, base_url="http://t"),
        )
    )
    engine = LifecycleEngine(
        registry=RegistryClient(client=registry, base_url="http://t"),
        delegation=delegation,
        ledger=LedgerClient(client=ledger, base_url="http://t"),
        killswitch=killswitch,
    )

    registry.post("/agents", json={
        "agent_id": "invoicing-agent", "name": "Invoicing",
        "owner": "AP Team Lead", "domain": "finance"})
    registry.post("/agents", json={
        "agent_id": "rogue-experiment", "name": "Rogue",
        "owner": "Departed Employee", "domain": "growth"})

    # token expiring in 10 days (inside 30-day horizon)
    delegation.post("/tokens", json={
        "agent_id": "invoicing-agent", "granted_by": "Controller Spin State",
        "scope": ["draft invoices"],
        "expires_at": (NOW + timedelta(days=10)).isoformat()})
    # token expiring in a year (outside horizon)
    delegation.post("/tokens", json={
        "agent_id": "invoicing-agent", "granted_by": "Controller Spin State",
        "scope": ["read timesheets"],
        "expires_at": (NOW + timedelta(days=365)).isoformat()})
    return engine, registry, ledger


def test_sweep_findings(stack):
    engine, _, ledger = stack
    report = engine.sweep(ROSTER, config=SweepConfig(), now=NOW)

    assert report.agents_scanned == 2
    assert report.roster_size == 2

    assert len(report.expiring) == 1
    assert report.expiring[0].days_left == 10

    # both records were just created — nothing is 90 days stale
    assert report.reattestation_due == []

    assert len(report.orphans) == 1
    orphan = report.orphans[0]
    assert orphan.agent_id == "rogue-experiment"
    assert orphan.auto_killed is False  # flag off by default

    types = [e["event_type"] for e in ledger.get("/events").json()]
    assert "lifecycle.expiring_authority" in types
    assert "lifecycle.orphan" in types
    assert report.escalations_written == 2


def test_reattestation_detected_for_stale_records(stack, tmp_path):
    engine, registry, _ = stack
    future = NOW + timedelta(days=120)
    report = engine.sweep(ROSTER, config=SweepConfig(), now=future)
    stale_ids = {r.agent_id for r in report.reattestation_due}
    assert "invoicing-agent" in stale_ids  # untouched for 120 > 90 days


def test_adversarial_auto_kill_requires_flag(stack):
    """The dangerous path must be opt-in: flag off ⇒ orphan stays active."""
    engine, registry, _ = stack
    engine.sweep(ROSTER, config=SweepConfig(auto_kill_orphans=False), now=NOW)
    assert registry.get("/agents/rogue-experiment").json()["status"] == "active"


def test_auto_kill_with_flag_kills_and_logs(stack):
    engine, registry, ledger = stack
    report = engine.sweep(
        ROSTER,
        config=SweepConfig(auto_kill_orphans=True, operator="CHRO sweep (test)"),
        now=NOW,
    )
    orphan = report.orphans[0]
    assert orphan.auto_killed is True
    assert registry.get("/agents/rogue-experiment").json()["status"] == "killed"

    kills = ledger.get("/events", params={"event_type": "kill.agent"}).json()
    assert len(kills) == 1
    assert "orphaned agent" in kills[0]["payload"]["reason"]


def test_sweep_idempotent_no_duplicate_kills(stack):
    engine, registry, ledger = stack
    cfg = SweepConfig(auto_kill_orphans=True)
    engine.sweep(ROSTER, config=cfg, now=NOW)
    report2 = engine.sweep(ROSTER, config=cfg, now=NOW)
    # second sweep: orphan already killed ⇒ not "active" ⇒ no second kill
    assert report2.orphans[0].auto_killed is False
    kills = ledger.get("/events", params={"event_type": "kill.agent"}).json()
    assert len(kills) == 1


def test_markdown_report(stack):
    engine, _, _ = stack
    md = render_markdown(engine.sweep(ROSTER, config=SweepConfig(), now=NOW))
    assert "# Lifecycle sweep report" in md
    assert "Expiring authorities (1)" in md
    assert "Orphans (1)" in md
    assert "auto-kill orphans: off" in md
    assert "no LLM" in md
