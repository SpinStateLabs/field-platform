"""v1.2 B4 — a retire must not be undoable by the kill-switch.

Before this guard, `/kill` flipped a retired agent to `killed` and `/revive`
then put it back to `active`: two clicks and a decommission was gone. `/drill`
was the same hole wearing a different name — it flips the record to `killed`
and its restore is allowed to fail. Each test here fails if someone removes
one of the four guards (`/kill`, `/revive`, `/kill/domain/{d}`, `/drill`).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

OP = {"operator": "CISO on-call", "reason": "test"}


@pytest.fixture()
def stack(tmp_path):
    store = RegistryStore(tmp_path / "agents.sqlite3")
    registry = TestClient(create_registry_app(store=store))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "e.jsonl")))
    kill = TestClient(
        create_kill_app(
            registry=RegistryClient(client=registry, base_url="http://t"),
            ledger=LedgerClient(client=ledger, base_url="http://t"),
        )
    )
    for agent_id, status in (("retired-agent", "retired"), ("live-agent", "active")):
        registry.post("/agents", json={"agent_id": agent_id, "name": agent_id,
                                       "owner": "Owner", "domain": "finance"})
        if status != "active":
            registry.patch(f"/agents/{agent_id}", json={"status": status})
    yield kill, registry, ledger
    store.close()


def test_adversarial_kill_of_a_retired_agent_is_409(stack):
    kill, registry, ledger = stack
    r = kill.post("/kill/retired-agent", json=OP)
    assert r.status_code == 409
    assert "retired" in str(r.json()["detail"])
    assert registry.get("/agents/retired-agent").json()["status"] == "retired"
    kills = ledger.get("/events", params={"event_type": "kill.agent"}).json()
    assert kills == []           # no event for a refusal


def test_adversarial_revive_of_a_retired_agent_is_409(stack):
    """The undo path: without this, one console click un-decommissions."""
    kill, registry, ledger = stack
    r = kill.post("/revive/retired-agent", json=OP)
    assert r.status_code == 409
    assert registry.get("/agents/retired-agent").json()["status"] == "retired"
    assert ledger.get("/events", params={"event_type": "kill.revive"}).json() == []


def test_adversarial_kill_then_revive_cannot_launder_a_retirement(stack):
    """The full two-step attack, end to end."""
    kill, registry, _ = stack
    assert kill.post("/kill/retired-agent", json=OP).status_code == 409
    assert kill.post("/revive/retired-agent", json=OP).status_code == 409
    assert registry.get("/agents/retired-agent").json()["status"] == "retired"


def test_domain_kill_skips_retired_and_still_kills_the_rest(stack):
    kill, registry, _ = stack
    r = kill.post("/kill/domain/finance", json=OP)
    assert r.status_code == 200
    report = r.json()
    assert report["killed"] == ["live-agent"]
    assert report["skipped_retired"] == ["retired-agent"]
    outcomes = {row["agent_id"]: row["outcome"] for row in report["results"]}
    assert outcomes["retired-agent"] == "skipped_retired"
    assert registry.get("/agents/retired-agent").json()["status"] == "retired"
    assert registry.get("/agents/live-agent").json()["status"] == "killed"


def test_revive_of_a_killed_agent_still_works(stack):
    """The guard must be about `retired`, not about every non-active status."""
    kill, registry, _ = stack
    kill.post("/kill/live-agent", json=OP)
    r = kill.post("/revive/live-agent", json=OP)
    assert r.status_code == 200 and r.json()["killed"] is False
    assert registry.get("/agents/live-agent").json()["status"] == "active"


def test_revive_of_an_unknown_agent_is_still_404(stack):
    kill, _, _ = stack
    assert kill.post("/revive/ghost-agent", json=OP).status_code == 404


def test_adversarial_drill_of_a_retired_agent_is_409(stack):
    """The fourth status-writing route — and the one that made the other
    three guards bypassable. A drill flips the record to `killed`; if the
    restore then fails the agent is left `killed`, and `/revive` accepts a
    killed agent. Drill-then-revive laundered a decommissioned agent back to
    `active` without ever touching a guarded route."""
    kill, registry, ledger = stack
    r = kill.post("/drill/retired-agent", json=OP)
    assert r.status_code == 409
    assert "retired" in str(r.json()["detail"])
    assert registry.get("/agents/retired-agent").json()["status"] == "retired"
    # a refused drill is not a drill: no start event, no kill
    assert ledger.get("/events", params={"event_type": "kill.drill.start"}).json() == []
    assert ledger.get("/events", params={"event_type": "kill.agent"}).json() == []


def test_adversarial_drill_then_revive_cannot_launder_a_retirement(stack):
    """The full laundering chain, end to end: 409 at the drill means the
    revive that followed it has nothing to revive."""
    kill, registry, _ = stack
    assert kill.post("/drill/retired-agent", json=OP).status_code == 409
    assert kill.post("/revive/retired-agent", json=OP).status_code == 409
    assert registry.get("/agents/retired-agent").json()["status"] == "retired"


def test_drill_of_an_active_agent_still_works_and_restores(stack):
    """The guard must be about `retired`, not about drills. Without this the
    409 above could be satisfied by breaking /drill outright."""
    kill, registry, _ = stack
    r = kill.post("/drill/live-agent", json=OP)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["restored"] is True
    assert body["restored_status"] == "active"
    assert registry.get("/agents/live-agent").json()["status"] == "active"


def test_drill_of_an_unknown_agent_is_still_404(stack):
    kill, _, _ = stack
    assert kill.post("/drill/ghost-agent", json=OP).status_code == 404
