"""B-S12-12: the domain filter is case- and padding-insensitive (read side).

A domain halt is a safety control: 'finance' must reach agents registered as
'Finance' or 'finance '. Padding can reach the store through paths that do
not strip it, so the rows are written through the store directly.
"""

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.models import AgentCreate
from agent_registry.store import RegistryStore


@pytest.fixture()
def store(tmp_path):
    s = RegistryStore(tmp_path / "agents.sqlite3")
    for agent_id, domain in (
        ("a-upper", "Finance"),
        ("a-padded", "finance "),
        ("a-lower", "finance"),
        ("a-other", "finances"),
        ("a-hr", "hr"),
    ):
        s.add(AgentCreate(agent_id=agent_id, name=agent_id, owner="o", domain=domain))
    return s


def test_store_list_matches_case_and_padding(store):
    ids = [r.agent_id for r in store.list(domain="finance")]
    assert ids == ["a-lower", "a-padded", "a-upper"]
    assert [r.agent_id for r in store.list(domain="  FINANCE ")] == ids


def test_http_filter_matches_the_store(store):
    client = TestClient(create_app(store=store))
    want = ["a-lower", "a-padded", "a-upper"]
    for q in ("finance", "FINANCE", "Finance"):
        r = client.get("/agents", params={"domain": q})
        assert r.status_code == 200
        assert [a["agent_id"] for a in r.json()] == want


def test_unrelated_domain_is_not_matched(store):
    assert [r.agent_id for r in store.list(domain="hr")] == ["a-hr"]
    assert store.list(domain="fin") == []
