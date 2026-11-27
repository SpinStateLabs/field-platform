"""S8-15: PATCH /agents/{id} that sends no field is a 422, not a 200 that ledgers an empty update.

`{}` built an empty column list, skipped the UPDATE (updated_at did not move) and still appended
`registry.updated {"fields": []}` and answered 200: audit noise that looks like a change. AgentUpdate now refuses a patch that
sends no field other than the condition (a named message, no echo). A field sent as an explicit null counts as sent and is
accepted as before; per-field omission stays allowed, and a patch equal to the current values is a real write that still
moves updated_at."""

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


def test_a_patch_that_sends_no_field_is_422_with_no_ledger_row_and_no_change(registry):
    client, ledger = registry
    before = client.get("/agents/invoicing-agent").json()
    r = client.patch("/agents/invoicing-agent", json={})
    assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body"]     # the handler drops the message text
    assert ledger.events == []
    assert client.get("/agents/invoicing-agent").json() == before


def test_the_refusal_does_not_echo_anything(registry):
    client, _ = registry
    r = client.patch("/agents/invoicing-agent", json={"name": None, "domain": None, "extra": MARK})
    assert r.status_code == 422 and MARK not in r.text


@pytest.mark.parametrize("body", [{"manifest_ref": None}, {"name": None},
                                  {"name": None, "owner": None, "domain": None, "manifest_ref": None, "status": None}],
                         ids=["ref-null", "name-null", "all-null"])
def test_an_explicit_null_is_a_field_sent_accepted_and_changes_no_column(registry, body):
    client, ledger = registry
    before = client.get("/agents/invoicing-agent").json()
    r = client.patch("/agents/invoicing-agent", json=body)
    assert r.status_code == 200 and r.json() == before            # updated_at included
    # as before this rule: the accepted patch is ledgered with no field named
    assert ledger.events == [("registry.updated", {"fields": []}, "invoicing-agent")]


def test_the_model_refuses_the_empty_patch_directly():
    with pytest.raises(ValidationError, match="at least one field"):
        AgentUpdate()
    assert AgentUpdate(name=None).model_fields_set == {"name"}
    assert AgentUpdate(domain="x").domain == "x"


@pytest.mark.parametrize("body", [{"domain": "ops"}, {"name": "Renamed"}, {"owner": "Someone Else"},
                                  {"status": "killed"}, {"manifest_ref": "manifests/invoicing.yaml"}, {"manifest_ref": ""}])
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


@pytest.mark.parametrize("stale", [False, True], ids=["current", "stale"])
def test_the_condition_alone_is_an_empty_patch(registry, stale):
    client, ledger = registry
    before = client.get("/agents/invoicing-agent").json()
    seen = "2000-01-01T00:00:00+00:00" if stale else before["updated_at"]
    r = client.patch("/agents/invoicing-agent", json={"if_updated_at": seen})
    assert r.status_code == 422 and r.json()["detail"][0]["loc"] == ["body"]
    assert ledger.events == []
    assert client.get("/agents/invoicing-agent").json() == before
    with pytest.raises(ValidationError, match="at least one field"):
        AgentUpdate(if_updated_at=seen)


def test_the_condition_with_one_field_still_applies_and_a_stale_one_is_412(registry):
    client, ledger = registry
    seen = client.get("/agents/invoicing-agent").json()["updated_at"]
    r = client.patch("/agents/invoicing-agent", json={"domain": "ops", "if_updated_at": seen})
    assert r.status_code == 200 and r.json()["domain"] == "ops"
    assert ledger.events[-1][1] == {"fields": ["domain"]}
    ledger.events.clear()
    r = client.patch("/agents/invoicing-agent", json={"domain": "legal", "if_updated_at": seen})
    assert r.status_code == 412
    assert client.get("/agents/invoicing-agent").json()["domain"] == "ops"
