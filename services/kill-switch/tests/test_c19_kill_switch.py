"""Phase G Stage 0, guards slice, C-19 (design 5.1 addendum, RT2-6, RT2-7), kill-switch
side: a halt that did not happen is never answered 2xx.

* ``POST /kill/domain/<d>`` for a domain with no registered agent (nonexistent or
  empty) is 404, never a 2xx with an empty tally (reviewer note PG0-CLIENTS-R1-04).

Real kill-switch + registry + sealed-ledger apps over TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

OP = {"operator": "CISO", "reason": "c19"}


class Stack:
    def __init__(self, tmp_path, registry_wrapper=None):
        self.registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "a.sqlite3")))
        self.ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "e.jsonl")))
        reg = RegistryClient(client=self.registry, base_url="http://t")
        self.kill = TestClient(create_kill_app(
            registry=registry_wrapper(reg) if registry_wrapper else reg,
            ledger=LedgerClient(client=self.ledger, base_url="http://t")))

    def register(self, agent_id, domain="finance"):
        assert self.registry.post("/agents", json={"agent_id": agent_id, "name": agent_id,
                                                   "owner": "O", "domain": domain}).status_code == 201

    def events(self, event_type):
        return self.ledger.get("/events", params={"event_type": event_type}).json()


@pytest.mark.parametrize("domain", ["no-such-domain", "finance"])
def test_a_domain_with_no_registered_agent_is_404_never_an_empty_2xx(tmp_path, domain):
    s = Stack(tmp_path)
    s.register("crm-agent", domain="sales")       # agents elsewhere, none in `domain`
    r = s.kill.post(f"/kill/domain/{domain}", json=OP)
    assert r.status_code == 404
    assert s.registry.get("/agents/crm-agent").json()["status"] == "active"
    assert s.events("kill.domain") == []
