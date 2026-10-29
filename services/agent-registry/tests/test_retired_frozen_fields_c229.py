"""C-229 (reviewer C-202, D-30 provisional): a retired agent's owner, domain and manifest_ref are
frozen (409); ``name`` stays editable; a live agent is unaffected. The rule lives in the store, in
the same atomic step as the retired-is-terminal rule, and the API maps it to 409."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.models import AgentStatus, AgentUpdate
from agent_registry.store import RegistryStore, RetiredAgentError, RetiredRecordFrozenError
from field_core import operator_auth as oa

FIELDS = {"owner": "New Owner", "domain": "support", "manifest_ref": "manifests/invoicing-agent.yaml"}


@pytest.fixture(autouse=True)
def _flags_off(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)


@pytest.fixture()
def env(tmp_path):
    store = RegistryStore(tmp_path / "a.sqlite3")
    c = TestClient(create_app(store=store))
    assert c.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O",
                                   "domain": "finance"}).status_code == 201
    return c, store


def _retire(c):
    assert c.patch("/agents/a1", json={"status": "retired"}).status_code == 200


@pytest.mark.parametrize("field", sorted(FIELDS))
def test_api_refuses_each_frozen_field_on_a_retired_agent(env, field):
    c, _ = env
    _retire(c)
    before = c.get("/agents/a1").json()
    r = c.patch("/agents/a1", json={field: FIELDS[field]})
    assert r.status_code == 409
    assert r.json()["detail"] == (f"agent 'a1' is retired - owner, domain and manifest_ref "
                                  "can no longer be edited")
    assert c.get("/agents/a1").json() == before  # nothing written, updated_at included


@pytest.mark.parametrize("field", sorted(FIELDS))
def test_store_refuses_each_frozen_field_on_a_retired_agent(env, field):
    _, store = env
    store.set_status("a1", AgentStatus.RETIRED)
    with pytest.raises(RetiredRecordFrozenError):
        store.update("a1", AgentUpdate(**{field: FIELDS[field]}))
    assert issubclass(RetiredRecordFrozenError, RetiredAgentError)


def test_a_mixed_patch_with_a_frozen_field_writes_nothing(env):
    c, _ = env
    _retire(c)
    before = c.get("/agents/a1").json()
    assert c.patch("/agents/a1", json={"name": "sneaky", "owner": "Mallory"}).status_code == 409
    assert c.get("/agents/a1").json() == before


def test_retiring_with_a_frozen_field_is_still_refused_once_retired(env):
    c, _ = env
    _retire(c)
    assert c.patch("/agents/a1", json={"status": "retired", "owner": "Mallory"}).status_code == 409


def test_name_stays_editable_on_a_retired_agent(env):
    c, _ = env
    _retire(c)
    r = c.patch("/agents/a1", json={"name": "renamed"})
    assert r.status_code == 200 and r.json()["name"] == "renamed" and r.json()["status"] == "retired"


@pytest.mark.parametrize("status", [AgentStatus.ACTIVE, AgentStatus.KILLED])
def test_a_live_agent_may_edit_every_field(env, status):
    c, store = env
    if status != AgentStatus.ACTIVE:
        store.set_status("a1", status)
    assert c.patch("/agents/a1", json={"owner": "New Owner", "domain": "support"}).status_code == 200

