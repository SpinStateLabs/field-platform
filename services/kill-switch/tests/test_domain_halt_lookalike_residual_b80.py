"""Backlog B80, the residual pinned (not assumed): a row whose domain is a look-alike of "finance", stored BEFORE the
registry's ASCII write rule (here written through the store, bypassing the model), is NOT reached by POST
/kill/domain/finance; the plain agent is. It stays active until a halt by id (or a fleet halt naming no domain) reaches
it. Real kill-switch + registry + sealed-ledger apps over TestClient."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.models import AgentCreate
from agent_registry.store import RegistryStore
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

OP = {"operator": "CISO", "reason": "b80"}
LOOKALIKES = ["fin" + chr(0x200B) + "ance", "fin" + chr(0x0430) + "nce", "fin  ance", chr(0xFF46) + "inance",
              "fina" + chr(0x0301) + "nce"]


@pytest.mark.parametrize("value", LOOKALIKES, ids=["zwsp", "cyrillic", "double-space", "fullwidth", "combining"])
def test_a_domain_halt_misses_a_stored_lookalike_and_a_halt_by_id_reaches_it(tmp_path, value):
    store = RegistryStore(tmp_path / "a.sqlite3")
    store.add(AgentCreate(agent_id="plain", name="P", owner="O", domain="finance"))
    store.add(AgentCreate.model_construct(agent_id="legacy", name="L", owner="O", domain=value, manifest_ref=None))
    registry = TestClient(create_registry_app(store=store))
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "e.jsonl")))
    kill = TestClient(create_kill_app(registry=RegistryClient(client=registry, base_url="http://t"),
                                      ledger=LedgerClient(client=ledger, base_url="http://t")))

    r = kill.post("/kill/domain/finance", json=OP)
    assert r.status_code == 200, r.text
    assert [x["agent_id"] for x in r.json()["results"]] == ["plain"]
    assert registry.get("/agents/plain").json()["status"] == "killed"
    assert registry.get("/agents/legacy").json()["status"] == "active"      # THE RESIDUAL: the named halt missed it

    assert kill.post("/kill/legacy", json=OP).status_code in (200, 201)      # the runbook fallback: halt by id
    assert registry.get("/agents/legacy").json()["status"] == "killed"
    store.close()
