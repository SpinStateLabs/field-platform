"""S8-15: PATCH /agents/{id} with no editable field is a 422, not a 200 that ledgers an empty update.

`{}` or only nulls built an empty column list, skipped the UPDATE (updated_at did not move) and still appended
`registry.updated {"fields": []}` and answered 200: audit noise that looks like a change. AgentUpdate now refuses a patch with
no non-None field (a named message, no echo). Per-field omission stays allowed, and a patch equal to the current values is a
real write that still moves updated_at."""

import time

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent_registry.api import create_app
from agent_registry.models import AgentUpdate
from agent_registry.store import RegistryStore

AGENT = {"agent_id": "invoicing-agent", "name": "Invoice Drafting Copilot",
         "owner": "Controller, Spin State Labs", "domain": "finance"}
MARK = "ZZ-MARKER"


class _Ledger:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload=None, agent_id=None):
        self.events.append((event_type, payload, agent_id))


@pytest.fixture()
def registry(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    ledger = _Ledger()
    client = TestClient(create_app(store=RegistryStore(tmp_path / "agents.sqlite3"), ledger=ledger))
    assert client.post("/agents", json=AGENT).status_code == 201
    ledger.events.clear()
    return client, ledger


@pytest.mark.parametrize("body", [{}, {"name": None}, {"owner": None, "domain": None},
                                  {"name": None, "owner": None, "domain": None, "manifest_ref": None, "status": None}],
                         ids=["empty", "one-null", "two-nulls", "all-null"])
def test_a_patch_with_no_non_null_field_is_422_with_no_ledger_row_and_no_change(registry, body):
    client, ledger = registry
    before = client.get("/agents/invoicing-agent").json()
    r = client.patch("/agents/invoicing-agent", json=body)
    assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body"]     # the handler drops the message text
    assert ledger.events == []
    assert client.get("/agents/invoicing-agent").json() == before


def test_the_refusal_does_not_echo_anything(registry):
    client, _ = registry
    r = client.patch("/agents/invoicing-agent", json={"name": None, "domain": None, "extra": MARK})
    assert r.status_code == 422 and MARK not in r.text


def test_the_model_refuses_the_empty_patch_directly():
    for kwargs in ({}, {"name": None}):
        with pytest.raises(ValidationError, match="at least one field"):
            AgentUpdate(**kwargs)
    assert AgentUpdate(domain="x").domain == "x"


@pytest.mark.parametrize("body", [{"domain": "ops"}, {"name": "Renamed"}, {"owner": "Someone Else"},
                                  {"status": "killed"}, {"manifest_ref": "manifests/invoicing.yaml"}, {"domain": ""}])
def test_a_real_single_field_patch_is_unchanged(registry, body):
    client, ledger = registry
    r = client.patch("/agents/invoicing-agent", json=body)
    assert r.status_code == 200
    assert [e[0] for e in ledger.events] in (["registry.updated"], ["registry.status_changed"])
    if "status" not in body:
        assert ledger.events[0][1] == {"fields": sorted(body)}


def test_a_patch_equal_to_the_current_values_is_a_real_write_that_moves_updated_at(registry):
    client, ledger = registry
    before = client.get("/agents/invoicing-agent").json()
    time.sleep(1.1)                                               # updated_at has whole-second resolution
    r = client.patch("/agents/invoicing-agent", json={"domain": before["domain"]})
    assert r.status_code == 200
    assert r.json()["updated_at"] > before["updated_at"]
    assert [e[0] for e in ledger.events] == ["registry.updated"]
