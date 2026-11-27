"""An empty ``name`` or ``owner`` is a 422 at the request model, on create
AND on PATCH.

``AgentRecord`` and ``AgentCreate`` required ``min_length=1`` on both fields
but ``AgentUpdate`` did not, so ``PATCH /agents/{id} {"owner": ""}`` passed
request validation. Before the OPEN-A atomicity fix it returned 200 and
persisted the empty owner, after which every GET of that record, GET /agents
and GET /health returned 500. After OPEN-A it returned 500 (the read-back
failed validation and rolled back). Neither is the right answer for a bad
request, and neither made "human owner required" true at the input boundary.
Now the request model rejects it: 422, the row unchanged, no ledger note.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent_registry.api import create_app
from agent_registry.models import AgentCreate, AgentUpdate
from agent_registry.store import RegistryStore

AGENT = {"agent_id": "invoicing-agent", "name": "Invoice Drafting Copilot",
         "owner": "Controller, Spin State Labs", "domain": "finance"}


class _Ledger:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, str | None]] = []

    def append(self, event_type, payload=None, agent_id=None):
        self.events.append((event_type, payload, agent_id))


@pytest.fixture()
def registry(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    store = RegistryStore(tmp_path / "agents.sqlite3")
    ledger = _Ledger()
    client = TestClient(create_app(store=store, ledger=ledger),
                        raise_server_exceptions=False)
    assert client.post("/agents", json=AGENT).status_code == 201
    yield client, ledger
    store.close()


@pytest.mark.parametrize("field", ["name", "owner"])
def test_patch_with_an_empty_name_or_owner_is_422_and_changes_nothing(registry, field):
    client, ledger = registry
    before = client.get(f"/agents/{AGENT['agent_id']}").json()
    notes_before = list(ledger.events)

    r = client.patch(f"/agents/{AGENT['agent_id']}", json={field: ""})

    assert r.status_code == 422, (r.status_code, r.text)
    assert any(err["loc"][-1] == field for err in r.json()["detail"]), r.json()
    assert client.get(f"/agents/{AGENT['agent_id']}").json() == before
    assert client.get("/agents").status_code == 200
    assert client.get("/health").status_code == 200
    assert ledger.events == notes_before  # no registry.updated note for a refusal


@pytest.mark.parametrize("field", ["name", "owner"])
def test_empty_field_in_a_multi_field_patch_rejects_the_whole_patch(registry, field):
    client, ledger = registry
    before = client.get(f"/agents/{AGENT['agent_id']}").json()
    r = client.patch(f"/agents/{AGENT['agent_id']}",
                     json={field: "", "status": "killed", "manifest_ref": "m.yaml"})
    assert r.status_code == 422
    assert client.get(f"/agents/{AGENT['agent_id']}").json() == before
    assert [e for e, _, _ in ledger.events].count("registry.status_changed") == 0


@pytest.mark.parametrize("field", ["name", "owner"])
def test_create_with_an_empty_name_or_owner_is_422(registry, field):
    client, _ = registry
    body = dict(AGENT, agent_id="second-agent", **{field: ""})
    r = client.post("/agents", json=body)
    assert r.status_code == 422
    assert client.get("/agents/second-agent").status_code == 404


@pytest.mark.parametrize("model", [AgentCreate, AgentUpdate])
@pytest.mark.parametrize("field", ["name", "owner"])
def test_request_models_reject_an_empty_name_or_owner(model, field):
    base = {"agent_id": "x", "name": "n", "owner": "o"} if model is AgentCreate else {}
    with pytest.raises(ValidationError):
        model(**dict(base, **{field: ""}))


def test_a_patch_may_still_omit_name_and_owner(registry):
    """min_length applies to a value that is sent, not to an omitted field:
    a status-only PATCH (every kill) must keep working."""
    client, _ = registry
    r = client.patch(f"/agents/{AGENT['agent_id']}", json={"status": "killed"})
    assert r.status_code == 200
    assert r.json()["name"] == AGENT["name"] and r.json()["owner"] == AGENT["owner"]
    assert AgentUpdate(name=None, owner=None).model_dump(exclude_none=True) == {}
