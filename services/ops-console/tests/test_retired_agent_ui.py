"""v1.2 B4 — the console must not offer `revive` for a decommissioned agent.

The enforceable guard is server-side (kill-switch answers 409); this is the
UI half, and it is tested so a later edit to the agents table cannot quietly
put the button back.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from ops_console.api import ServiceClient, create_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore


def wrap(test_client) -> ServiceClient:
    return ServiceClient(client=test_client, base_url="http://t")


@pytest.fixture()
def console_stack(tmp_path):
    store = RegistryStore(tmp_path / "agents.sqlite3")
    registry = TestClient(create_registry_app(store=store))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "e.jsonl")))
    killswitch = TestClient(
        create_kill_app(
            registry=RegistryClient(client=registry, base_url="http://t"),
            ledger=LedgerClient(client=ledger, base_url="http://t")))
    console = TestClient(create_app(
        registry=wrap(registry), ledger=wrap(ledger),
        delegation=wrap(registry), governor=wrap(registry),
        killswitch=wrap(killswitch), sentinel=wrap(registry)))
    registry.post("/agents", json={"agent_id": "retired-agent", "name": "R",
                                   "owner": "Owner", "domain": "finance"})
    registry.patch("/agents/retired-agent", json={"status": "retired"})
    yield console, registry
    store.close()


def test_console_page_has_no_revive_button_for_retired_agents(console_stack):
    console, _ = console_stack
    html = console.get("/").text
    # The agents-table action cell must branch on "retired" BEFORE it falls
    # through to the revive button.
    start = html.index("function renderAgents(sec)")
    actions = html[start:html.index("function tokState", start)]
    assert 'a.status === "retired"' in actions
    retired_branch = actions.index('a.status === "retired"')
    revive_button = actions.index("reviveAgent(")
    assert retired_branch < revive_button, "retired must be handled before revive"
    assert "decommissioned" in actions


def test_console_revive_of_a_retired_agent_is_refused_by_the_killswitch(console_stack):
    """Even if a stale browser tab still shows the button, the click fails."""
    console, registry = console_stack
    r = console.post("/api/agents/retired-agent/revive",
                     json={"operator": "CISO via console", "reason": "oops"})
    assert r.status_code == 409
    assert registry.get("/agents/retired-agent").json()["status"] == "retired"
