"""agent-registry tests: CRUD, discovery scanner, adversarial spoof case."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.store import RegistryStore

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(store=RegistryStore(tmp_path / "agents.sqlite3")))


def register_invoicing_agent(client):
    r = client.post(
        "/agents",
        json={
            "agent_id": "invoicing-agent",
            "name": "Invoice Drafting Copilot",
            "owner": "Controller, Spin State Labs",
            "domain": "finance",
            "manifest_ref": "manifests/invoicing-agent.yaml",
        },
    )
    assert r.status_code == 201
    return r.json()


def test_crud_roundtrip(client):
    register_invoicing_agent(client)

    r = client.get("/agents/invoicing-agent")
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    r = client.patch("/agents/invoicing-agent", json={"status": "killed"})
    assert r.json()["status"] == "killed"

    killed = client.get("/agents", params={"status": "killed"}).json()
    assert [a["agent_id"] for a in killed] == ["invoicing-agent"]


def test_duplicate_registration_conflicts(client):
    register_invoicing_agent(client)
    r = client.post(
        "/agents",
        json={"agent_id": "invoicing-agent", "name": "x", "owner": "y"},
    )
    assert r.status_code == 409


def test_unknown_agent_404(client):
    assert client.get("/agents/ghost").status_code == 404


def test_invalid_agent_id_rejected(client):
    r = client.post(
        "/agents",
        json={"agent_id": "Not A Slug!", "name": "x", "owner": "y"},
    )
    assert r.status_code == 422


def test_discovery_finds_shadow_agents(client):
    """The two AI workflows + automation accounts surface; registered ones don't."""
    register_invoicing_agent(client)
    n8n = json.loads((FIXTURES / "n8n-export.json").read_text(encoding="utf-8"))
    accounts = (FIXTURES / "service-accounts.csv").read_text(encoding="utf-8")

    r = client.post("/discover", json={"n8n_export": n8n, "accounts_csv": accounts})
    assert r.status_code == 200
    report = r.json()

    assert report["scanned_workflows"] == 3
    assert report["scanned_accounts"] == 6
    ids = {c["identifier"] for c in report["candidates"]}

    # Registered agent's workflow and account are matched, hence absent.
    assert "wf-101" not in ids            # "Invoice Drafting Copilot" is registered
    assert "svc-invoicing-agent" not in ids

    # AI workflow with no registration surfaces; plain backup workflow doesn't.
    assert "wf-103" in ids                # Support Ticket Summarizer
    assert "wf-102" not in ids            # Nightly DB Backup has no AI nodes

    # Automation-pattern accounts surface; humans don't.
    assert {"bot-crm-enrich", "svc-db-backup", "ai-pricing-experiment"} <= ids
    assert "jsmith" not in ids and "mchen" not in ids

    assert "no LLM" in report["method"]


def test_adversarial_renamed_workflow_still_flagged(client):
    """Adversarial: a shadow agent renamed to look mundane is still caught —
    detection keys on node *types*, not the workflow's display name."""
    register_invoicing_agent(client)
    sneaky = {
        "id": "wf-999",
        "name": "Weekly Report Formatter",  # innocuous name
        "nodes": [
            {"name": "Step 1", "type": "n8n-nodes-base.readBinaryFile"},
            {"name": "Step 2", "type": "@n8n/n8n-nodes-langchain.agent"},
        ],
    }
    r = client.post("/discover", json={"n8n_export": [sneaky]})
    report = r.json()
    assert len(report["candidates"]) == 1
    assert report["candidates"][0]["identifier"] == "wf-999"
    assert "agent" in report["candidates"][0]["evidence"]["ai_nodes"]


def test_discover_requires_input(client):
    assert client.post("/discover", json={}).status_code == 422
