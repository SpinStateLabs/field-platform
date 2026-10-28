"""C-167 (reviewer C-165 F-C165-1/-2, D-22): a retired agent cannot leave ``retired`` through the
store, and a decommission that commits between the API guard's read and its write is not overwritten.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.models import AgentStatus, AgentUpdate
from agent_registry.store import RegistryStore, RetiredAgentError
from field_core import operator_auth as oa


@pytest.fixture(autouse=True)
def _flags_off(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def store(tmp_path):
    s = RegistryStore(tmp_path / "a.sqlite3")
    c = TestClient(create_app(store=s))
    assert c.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O",
                                   "domain": "finance"}).status_code == 201
    return s


def _status(s):
    return s.get("a1").status


def test_store_refuses_to_move_a_retired_agent_out_of_retired(store):
    store.set_status("a1", AgentStatus.RETIRED)
    for target in (AgentStatus.ACTIVE, AgentStatus.KILLED):
        with pytest.raises(RetiredAgentError):
            store.set_status("a1", target)
        assert _status(store) == AgentStatus.RETIRED, target


def test_store_allows_retired_to_retired_and_other_fields_on_a_retired_agent(store):
    store.set_status("a1", AgentStatus.RETIRED)
    assert store.set_status("a1", AgentStatus.RETIRED).status == AgentStatus.RETIRED
    after = store.update("a1", AgentUpdate(name="renamed"))
    assert after.name == "renamed" and after.status == AgentStatus.RETIRED


def test_a_refused_move_out_of_retired_writes_nothing(store):
    store.set_status("a1", AgentStatus.RETIRED)
    stamp = store.get("a1").updated_at
    with pytest.raises(RetiredAgentError):
        store.update("a1", AgentUpdate(status=AgentStatus.ACTIVE, name="sneaky"))
    after = store.get("a1")
    assert after.name == "a1" and after.updated_at == stamp  # the refused patch rolled back whole


def test_a_killed_agent_can_still_be_revived_and_retired(store):
    store.set_status("a1", AgentStatus.KILLED)
    assert store.set_status("a1", AgentStatus.ACTIVE).status == AgentStatus.ACTIVE
    assert store.set_status("a1", AgentStatus.RETIRED).status == AgentStatus.RETIRED


def test_decommission_between_the_api_guard_read_and_the_write_is_not_overwritten(store, monkeypatch):
    """F-C165-1: the guard sees ``killed`` and lets PATCH status=active through; a decommission
    commits before the write; the write must be refused (409), not replace retired with active."""
    store.set_status("a1", AgentStatus.KILLED)
    client = TestClient(create_app(store=store))
    real_get = RegistryStore.get
    fired = []

    def racing_get(self, agent_id):
        record = real_get(self, agent_id)
        if not fired:
            fired.append(1)
            RegistryStore.set_status(self, agent_id, AgentStatus.RETIRED)  # the racing writer
        return record

    monkeypatch.setattr(RegistryStore, "get", racing_get)
    r = client.patch("/agents/a1", json={"status": "active"})
    monkeypatch.setattr(RegistryStore, "get", real_get)
    assert fired, "the interleaving did not run: the API guard no longer reads the record first"
    assert r.status_code == 409 and _status(store) == AgentStatus.RETIRED
