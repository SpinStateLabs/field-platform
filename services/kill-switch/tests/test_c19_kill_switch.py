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


# --- C-19 held-back half: every attempt errored => 502; drill not restored => 500 -----------------


class _Writes:
    """The kill-switch's registry: reads work; status writes to `fail_on` fail as a
    registry 401 would (the S1 failure: the kill-switch's identity missing or revoked)."""

    def __init__(self, fail_on):
        self.fail_on = fail_on

    def __call__(self, inner):
        fail_on = self.fail_on

        class W:
            def get_agent(self, agent_id):
                return inner.get_agent(agent_id)

            def list_agents(self, **kw):
                return inner.list_agents(**kw)

            def set_status(self, agent_id, status):
                if status in fail_on:
                    from field_core.clients import RegistryUnreachableError
                    raise RegistryUnreachableError("registry returned 401: operator credentials required")
                return inner.set_status(agent_id, status)
        return W()


def test_a_domain_kill_where_every_attempt_errored_is_502_with_the_report(tmp_path):
    s = Stack(tmp_path, registry_wrapper=_Writes(("killed",)))
    s.register("a1")
    s.register("a2")
    r = s.kill.post("/kill/domain/finance", json=OP)
    assert r.status_code == 502
    report = r.json()["detail"]
    assert report["killed"] == [] and report["already_killed"] == []
    assert [x["outcome"] for x in report["results"]] == ["error", "error"]
    assert all("502" in x["error"] for x in report["results"])
    for a in ("a1", "a2"):
        assert s.registry.get(f"/agents/{a}").json()["status"] == "active"
    [ev] = s.events("kill.domain")                   # the attempt is still ledgered
    assert ev["payload"]["killed"] == []


def test_a_domain_kill_with_one_success_stays_200(tmp_path):
    class OneFails(_Writes):
        def __call__(self, inner):
            w = super().__call__(inner)
            real = w.set_status

            def set_status(agent_id, status):
                if agent_id == "a2":
                    from field_core.clients import RegistryUnreachableError
                    raise RegistryUnreachableError("simulated")
                return real(agent_id, status)
            w.set_status = set_status
            return w

    s = Stack(tmp_path, registry_wrapper=OneFails(()))
    s.register("a1")
    s.register("a2")
    r = s.kill.post("/kill/domain/finance", json=OP)
    assert r.status_code == 200 and r.json()["killed"] == ["a1"]


def test_a_domain_kill_of_already_killed_agents_stays_200(tmp_path):
    s = Stack(tmp_path)
    s.register("a1")
    assert s.kill.post("/kill/a1", json=OP).status_code == 200
    r = s.kill.post("/kill/domain/finance", json=OP)
    assert r.status_code == 200 and r.json()["already_killed"] == ["a1"]


def test_a_domain_of_only_retired_agents_stays_200_with_nothing_attempted(tmp_path):
    s = Stack(tmp_path)
    s.register("a1")
    assert s.registry.patch("/agents/a1", json={"status": "retired"}).status_code == 200
    r = s.kill.post("/kill/domain/finance", json=OP)
    assert r.status_code == 200 and r.json()["skipped_retired"] == ["a1"]


def test_a_drill_that_could_not_restore_is_500_with_the_report(tmp_path):
    s = Stack(tmp_path, registry_wrapper=_Writes(("active",)))
    s.register("a1")
    r = s.kill.post("/drill/a1", json=OP)
    assert r.status_code == 500
    report = r.json()["detail"]
    assert report["restored"] is False and report["restored_status"] == "<restore failed>"
    assert s.registry.get("/agents/a1").json()["status"] == "killed"     # the fact reported
    assert len(s.events("kill.drill.restore_failed")) == 1
    assert len(s.events("kill.drill.complete")) == 1                     # still ledgered


def test_a_drill_that_restored_stays_200(tmp_path):
    s = Stack(tmp_path)
    s.register("a1")
    r = s.kill.post("/drill/a1", json=OP)
    assert r.status_code == 200 and r.json()["restored"] is True
