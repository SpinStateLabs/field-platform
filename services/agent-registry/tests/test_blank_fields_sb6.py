"""A whitespace-only name, owner or domain is a 422 on create and on PATCH, and a padded
value is stored stripped (scout S-B6). `min_length=1` let "   " through: an agent with a
blank "human owner" (the registry's one hard rule), and a domain of " finance" that the
kill-switch's exact-match domain halt for "finance" would silently miss. AgentRecord is
left alone on purpose: tightening the READ model would 500 every list over a legacy row."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agent_registry.api import create_app
from agent_registry.models import AgentCreate, AgentUpdate
from agent_registry.store import RegistryStore

AGENT = {"agent_id": "invoicing-agent", "name": "Invoice Drafting Copilot",
         "owner": "Controller", "domain": "finance"}
BLANK = ["", " ", "   ", "\t", "\n", " \t\n "]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    store = RegistryStore(tmp_path / "agents.sqlite3")
    c = TestClient(create_app(store=store), raise_server_exceptions=False)
    assert c.post("/agents", json=AGENT).status_code == 201
    yield c
    store.close()


@pytest.mark.parametrize("field", ["name", "owner", "domain"])
@pytest.mark.parametrize("blank", BLANK)
def test_create_with_a_blank_field_is_refused(field, blank):
    with pytest.raises(ValidationError):
        AgentCreate(**{**AGENT, "agent_id": "x1", field: blank})


@pytest.mark.parametrize("field", ["name", "owner", "domain"])
@pytest.mark.parametrize("blank", BLANK)
def test_update_with_a_blank_field_is_refused(field, blank):
    with pytest.raises(ValidationError):
        AgentUpdate(**{field: blank})


@pytest.mark.parametrize("field", ["name", "owner", "domain"])
def test_patch_over_http_with_whitespace_is_422_and_changes_nothing(client, field):
    before = client.get("/agents/invoicing-agent").json()
    r = client.patch("/agents/invoicing-agent", json={field: "   "})
    assert r.status_code == 422, r.text
    assert client.get("/agents/invoicing-agent").json() == before


@pytest.mark.parametrize("field", ["name", "owner", "domain"])
def test_post_over_http_with_whitespace_is_422(client, field):
    r = client.post("/agents", json={**AGENT, "agent_id": "second", field: "  "})
    assert r.status_code == 422, r.text
    assert client.get("/agents/second").status_code == 404


def test_surrounding_whitespace_is_stripped_on_create(client):
    r = client.post("/agents", json={**AGENT, "agent_id": "padded", "domain": " finance ",
                                     "owner": "  Controller ", "name": " N "})
    assert r.status_code == 201
    got = client.get("/agents/padded").json()
    assert (got["domain"], got["owner"], got["name"]) == ("finance", "Controller", "N")
    assert [a["agent_id"] for a in client.get("/agents", params={"domain": "finance"}).json()
            ].count("padded") == 1


def test_surrounding_whitespace_is_stripped_on_patch(client):
    r = client.patch("/agents/invoicing-agent", json={"domain": " hr "})
    assert r.status_code == 200 and r.json()["domain"] == "hr"


def test_omitted_fields_on_patch_stay_allowed_and_unchanged(client):
    r = client.patch("/agents/invoicing-agent", json={"name": "Renamed"})
    assert r.status_code == 200
    got = client.get("/agents/invoicing-agent").json()
    assert (got["name"], got["owner"], got["domain"]) == ("Renamed", "Controller", "finance")


def test_the_default_domain_is_unchanged(client):
    body = {k: v for k, v in AGENT.items() if k != "domain"}
    assert client.post("/agents", json={**body, "agent_id": "dflt"}).status_code == 201
    assert client.get("/agents/dflt").json()["domain"] == "general"
