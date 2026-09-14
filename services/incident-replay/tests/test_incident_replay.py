"""incident-replay tests: reconstruction, RACI, adversarial tampered ledger."""

import json
import os
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.clients import LedgerClient, RegistryClient
from field_core.templates_api import template_data
from incident_replay.api import create_app as create_replay_app
from incident_replay.engine import (
    LedgerQueryClient,
    ReplayEngine,
    TokenQueryClient,
    render_markdown,
)
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

WINDOW = {"since": "2020-01-01T00:00:00+00:00", "until": "2030-01-01T00:00:00+00:00"}


@pytest.fixture()
def stack(tmp_path):
    ledger_store = LedgerStore(tmp_path / "events.jsonl")
    registry = TestClient(
        create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3"))
    )
    ledger = TestClient(create_ledger_app(store=ledger_store))
    delegation = TestClient(
        create_delegation_app(
            store=TokenStore(tmp_path / "tokens.sqlite3"),
            ledger=LedgerClient(client=ledger, base_url="http://t"),
            registry=RegistryClient(client=registry, base_url="http://t"),
        )
    )
    replay = TestClient(
        create_replay_app(
            engine=ReplayEngine(
                ledger=LedgerQueryClient(client=ledger, base_url="http://t"),
                registry=RegistryClient(client=registry, base_url="http://t"),
                delegation=TokenQueryClient(client=delegation, base_url="http://t"),
            )
        )
    )

    # v1.2 D3b: POST /agents refuses a manifest_ref that does not resolve under
    # FIELD_MANIFEST_DIR. The agent registers while a valid manifest is there,
    # and the file is removed afterwards, so the replay meets the same state as
    # before D3b — a record whose ref no longer resolves (tests/conftest.py's
    # empty FIELD_MANIFEST_DIR) — and the RACI below keeps its clause defaults.
    manifest = Path(os.environ["FIELD_MANIFEST_DIR"]) / "manifests" / "invoicing-agent.yaml"
    manifest.parent.mkdir(parents=True)
    data = template_data("default")
    data["agent"]["name"] = "invoicing-agent"
    manifest.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    assert registry.post(
        "/agents",
        json={"agent_id": "invoicing-agent", "name": "Invoice Drafting Copilot",
              "owner": "AP Team Lead", "domain": "finance",
              "manifest_ref": "manifests/invoicing-agent.yaml"},
    ).status_code == 201
    manifest.unlink()
    manifest.parent.rmdir()
    delegation.post(
        "/tokens",
        json={"agent_id": "invoicing-agent",
              "granted_by": "Controller, Spin State Labs",
              "scope": ["draft invoices"], "ttl_seconds": 86400},
    )
    # Simulate the incident trail the sentinel would have written.
    for event_type, payload in (
        ("conformance.allow", {"action": "draft invoices", "clause_id": None}),
        ("conformance.allow", {"action": "draft invoices", "clause_id": None}),
        ("conformance.block", {"action": "transfer funds", "clause_id": "D.scope",
                               "reasons": ["'transfer funds' not in token scope"]}),
        ("kill.agent", {"operator": "CISO on-call", "reason": "scope probing"}),
    ):
        ledger.post("/events", json={"event_type": event_type,
                                     "agent_id": "invoicing-agent",
                                     "payload": payload})
    return replay, ledger_store, tmp_path


def test_replay_reconstructs_incident(stack):
    replay, _, _ = stack
    pm = replay.post(
        "/replay", json={"agent_id": "invoicing-agent", **WINDOW}
    ).json()

    assert pm["ledger_integrity_ok"] is True
    assert pm["agent_record"]["owner"] == "AP Team Lead"

    assert len(pm["authority"]) == 1
    assert pm["authority"][0]["granted_by"] == "Controller, Spin State Labs"

    types = [t["event_type"] for t in pm["timeline"]]
    assert types == ["delegation.mint", "conformance.allow", "conformance.allow",
                     "conformance.block", "kill.agent"]

    assert pm["first_failure"]["clause_id"] == "D.scope"
    assert pm["counts"]["conformance.allow"] == 2

    raci = pm["raci"]
    assert "AP Team Lead" in raci["Responsible"]
    assert "Controller" in raci["Accountable"]
    assert "GC" in raci["Consulted"]  # D-clause failure consults General Counsel


def test_markdown_report_is_raci_ready(stack):
    replay, _, _ = stack
    md = replay.post(
        "/replay/markdown", json={"agent_id": "invoicing-agent", **WINDOW}
    ).text
    assert "# Post-mortem — invoicing-agent" in md
    assert "## Who granted authority" in md
    assert "Controller, Spin State Labs" in md
    assert "`D.scope`" in md
    assert "| Responsible |" in md or "| Role | Party |" in md
    assert "no LLM" in md


def test_window_filters_events(stack):
    replay, _, _ = stack
    pm = replay.post(
        "/replay",
        json={"agent_id": "invoicing-agent",
              "since": "2031-01-01T00:00:00+00:00",
              "until": "2032-01-01T00:00:00+00:00"},
    ).json()
    assert pm["timeline"] == []
    assert pm["first_failure"] is None


def test_unregistered_agent_flagged_not_crash(stack):
    replay, _, _ = stack
    pm = replay.post("/replay", json={"agent_id": "ghost", **WINDOW}).json()
    assert pm["agent_record"] is None
    assert "unregistered" in pm["raci"]["Responsible"]


def test_adversarial_tampered_ledger_flagged_loudly(stack):
    """Adversarial: quiet edit of the incident trail must brand the report."""
    replay, ledger_store, tmp_path = stack
    path = tmp_path / "events.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[2])
    rec["payload"]["action"] = "totally innocent action"
    lines[2] = json.dumps(rec)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    pm = replay.post(
        "/replay", json={"agent_id": "invoicing-agent", **WINDOW}
    ).json()
    assert pm["ledger_integrity_ok"] is False
    assert "CHAIN BROKEN" in pm["ledger_integrity_detail"]

    md = replay.post(
        "/replay/markdown", json={"agent_id": "invoicing-agent", **WINDOW}
    ).text
    assert "LEDGER INTEGRITY FAILED" in md
    assert "cannot be treated as trustworthy evidence" in md
