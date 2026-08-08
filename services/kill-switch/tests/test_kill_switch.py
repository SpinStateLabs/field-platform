"""kill-switch tests: kill, domain kill, heartbeat, drill, adversarial cases."""

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore


class DownClient:
    def post(self, *a, **k):
        raise ConnectionError("down")

    def get(self, *a, **k):
        raise ConnectionError("down")

    def patch(self, *a, **k):
        raise ConnectionError("down")


@pytest.fixture()
def stack(tmp_path):
    registry_client = TestClient(
        create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3"))
    )
    ledger_client = TestClient(
        create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl"))
    )
    kill_client = TestClient(
        create_kill_app(
            registry=RegistryClient(client=registry_client, base_url="http://t"),
            ledger=LedgerClient(client=ledger_client, base_url="http://t"),
        )
    )
    for agent_id, domain in (
        ("invoicing-agent", "finance"),
        ("forecast-agent", "finance"),
        ("crm-agent", "sales"),
    ):
        registry_client.post(
            "/agents",
            json={"agent_id": agent_id, "name": agent_id, "owner": "Owner",
                  "domain": domain},
        )
    return kill_client, registry_client, ledger_client


OP = {"operator": "CISO on-call", "reason": "anomalous behavior"}


def test_kill_agent_flips_registry_and_logs(stack):
    kill_client, registry_client, ledger_client = stack
    r = kill_client.post("/kill/invoicing-agent", json=OP)
    assert r.status_code == 200
    report = r.json()
    assert report["previous_status"] == "active"
    assert report["elapsed_ms"] < 5000

    assert registry_client.get("/agents/invoicing-agent").json()["status"] == "killed"
    events = ledger_client.get("/events", params={"event_type": "kill.agent"}).json()
    assert len(events) == 1
    assert events[0]["payload"]["operator"] == "CISO on-call"


def test_heartbeat_reflects_kill(stack):
    kill_client, _, _ = stack
    assert kill_client.get("/heartbeat/invoicing-agent").json()["killed"] is False
    kill_client.post("/kill/invoicing-agent", json=OP)
    hb = kill_client.get("/heartbeat/invoicing-agent").json()
    assert hb["killed"] is True and hb["status"] == "killed"


def test_adversarial_unknown_agent_heartbeat_says_stop(stack):
    """Fail closed: an agent the registry doesn't know is told to halt."""
    kill_client, _, _ = stack
    hb = kill_client.get("/heartbeat/ghost-agent").json()
    assert hb["killed"] is True and hb["status"] == "unregistered"


def test_kill_domain_kills_only_that_domain(stack):
    kill_client, registry_client, _ = stack
    r = kill_client.post("/kill/domain/finance", json=OP)
    report = r.json()
    assert sorted(report["killed"]) == ["forecast-agent", "invoicing-agent"]
    assert registry_client.get("/agents/crm-agent").json()["status"] == "active"


def test_kill_is_idempotent(stack):
    kill_client, _, _ = stack
    kill_client.post("/kill/invoicing-agent", json=OP)
    r = kill_client.post("/kill/invoicing-agent", json=OP)
    assert r.status_code == 200
    assert r.json()["previous_status"] == "killed"
    d = kill_client.post("/kill/domain/finance", json=OP).json()
    assert "invoicing-agent" in d["already_killed"]


def test_drill_kills_verifies_and_restores(stack):
    kill_client, registry_client, ledger_client = stack
    r = kill_client.post("/drill/invoicing-agent", json=OP)
    assert r.status_code == 200
    report = r.json()
    assert report["restored"] is True
    assert report["restored_status"] == "active"
    assert 0 < report["kill_confirmed_ms"] <= report["total_ms"]

    # after the drill the agent is live again
    assert registry_client.get("/agents/invoicing-agent").json()["status"] == "active"
    types = [e["event_type"] for e in ledger_client.get("/events").json()]
    assert "kill.drill.start" in types and "kill.drill.complete" in types


def test_adversarial_kill_with_registry_down_fails_loud(tmp_path):
    """A kill that cannot reach the registry must error, never pretend."""
    ledger_client = TestClient(
        create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl"))
    )
    kill_client = TestClient(
        create_kill_app(
            registry=RegistryClient(client=DownClient(), base_url="http://t"),
            ledger=LedgerClient(client=ledger_client, base_url="http://t"),
        )
    )
    r = kill_client.post("/kill/invoicing-agent", json=OP)
    assert r.status_code == 502
    assert "cannot kill" in r.json()["detail"]


def test_kill_survives_ledger_outage(tmp_path):
    """Act-first: the halt succeeds even when the audit trail is down."""
    registry_client = TestClient(
        create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3"))
    )
    registry_client.post(
        "/agents",
        json={"agent_id": "invoicing-agent", "name": "x", "owner": "y"},
    )
    kill_client = TestClient(
        create_kill_app(
            registry=RegistryClient(client=registry_client, base_url="http://t"),
            ledger=LedgerClient(client=DownClient(), base_url="http://t"),
        )
    )
    r = kill_client.post("/kill/invoicing-agent", json=OP)
    assert r.status_code == 200
    assert registry_client.get("/agents/invoicing-agent").json()["status"] == "killed"
