"""Compare-and-set PATCH (kill-path hardening): ``if_updated_at`` applies the patch only if the row's updated_at still
equals it; any other write in between is a 412 and the row is left as that write set it. Two writes never share an
updated_at (strictly increasing per row), so even two kills in one clock tick differ."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.store import RegistryStore


@pytest.fixture()
def client(tmp_path):
    c = TestClient(create_app(store=RegistryStore(tmp_path / "a.sqlite3")))
    assert c.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O", "domain": "d"}).status_code == 201
    return c


def test_a_patch_with_the_current_version_applies_and_returns_a_new_version(client):
    v0 = client.get("/agents/a1").json()["updated_at"]
    r = client.patch("/agents/a1", json={"status": "killed", "if_updated_at": v0})
    assert r.status_code == 200 and r.json()["status"] == "killed" and r.json()["updated_at"] != v0


def test_a_patch_with_a_stale_version_is_412_and_changes_nothing(client):
    v0 = client.get("/agents/a1").json()["updated_at"]
    assert client.patch("/agents/a1", json={"status": "killed"}).status_code == 200      # someone else writes
    r = client.patch("/agents/a1", json={"status": "active", "if_updated_at": v0})
    assert r.status_code == 412
    assert client.get("/agents/a1").json()["status"] == "killed"


def test_a_rewrite_with_the_same_status_still_moves_the_version(client):
    client.patch("/agents/a1", json={"status": "killed"})
    v1 = client.get("/agents/a1").json()["updated_at"]
    client.patch("/agents/a1", json={"status": "killed"})
    v2 = client.get("/agents/a1").json()["updated_at"]
    assert v2 > v1
    assert client.patch("/agents/a1", json={"status": "active", "if_updated_at": v1}).status_code == 412


def test_many_rapid_writes_never_repeat_a_version(client):
    seen = {client.get("/agents/a1").json()["updated_at"]}
    for _ in range(50):
        seen.add(client.patch("/agents/a1", json={"status": "killed"}).json()["updated_at"])
    assert len(seen) == 51


@pytest.mark.parametrize("bad", ["", "yesterday", "2026-13-45T00:00:00Z", "x" * 100])
def test_an_unparseable_condition_is_422(client, bad):
    assert client.patch("/agents/a1", json={"status": "killed", "if_updated_at": bad}).status_code == 422


def test_the_z_suffix_form_of_the_version_is_accepted(client):
    v0 = client.get("/agents/a1").json()["updated_at"]
    z = v0.replace("+00:00", "Z") if "+00:00" in v0 else v0
    assert client.patch("/agents/a1", json={"status": "killed", "if_updated_at": z}).status_code == 200


def test_a_missing_agent_is_still_404_and_a_rename_with_a_condition_applies(client):
    v0 = client.get("/agents/a1").json()["updated_at"]
    assert client.patch("/agents/a1", json={"name": "renamed", "if_updated_at": v0}).status_code == 200
    assert client.patch("/agents/ghost", json={"status": "killed", "if_updated_at": v0}).status_code == 404


def test_a_conditional_patch_cannot_reactivate_a_retired_agent(client):
    client.patch("/agents/a1", json={"status": "retired"})
    v = client.get("/agents/a1").json()["updated_at"]
    assert client.patch("/agents/a1", json={"status": "active", "if_updated_at": v}).status_code == 409


# --- review round 4 (roley.reviewer F4, F5) ---------------------------------------------------------------------------


def test_F4_attest_never_moves_the_row_version_backwards_on_a_clock_step_back(tmp_path):
    from datetime import timedelta

    from agent_registry.models import AgentCreate
    store = RegistryStore(tmp_path / "s.sqlite3")
    store.add(AgentCreate(agent_id="a1", name="a1", owner="O", domain="d"))
    before = store.get("a1").updated_at
    after = store.attest("a1", "Don", now=before - timedelta(hours=1)).updated_at
    assert after > before, "a clock that stepped back moved the row version backwards"
    again = store.attest("a1", "Don", now=before - timedelta(hours=2)).updated_at
    assert again > after


def test_F4_attest_with_the_same_instant_twice_still_moves_the_version(tmp_path):
    from agent_registry.models import AgentCreate
    store = RegistryStore(tmp_path / "s.sqlite3")
    store.add(AgentCreate(agent_id="a1", name="a1", owner="O", domain="d"))
    t = store.get("a1").updated_at
    v1 = store.attest("a1", "Don", now=t).updated_at
    v2 = store.attest("a1", "Don", now=t).updated_at
    assert v1 > t and v2 > v1


def test_F5_a_legacy_row_with_a_timezone_less_updated_at_can_still_be_killed_and_read(tmp_path):
    store = RegistryStore(tmp_path / "s.sqlite3")
    c = TestClient(create_app(store=store))
    assert c.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O", "domain": "d"}).status_code == 201
    store._conn.execute("UPDATE agents SET updated_at=? WHERE agent_id=?", ("2026-01-01T00:00:00", "a1"))
    store._conn.commit()
    assert c.get("/agents/a1").status_code == 200
    r = c.patch("/agents/a1", json={"status": "killed"})
    assert r.status_code == 200 and r.json()["status"] == "killed"
    v = r.json()["updated_at"]
    assert c.patch("/agents/a1", json={"status": "active", "if_updated_at": v}).status_code == 200
    # and a conditional write against the legacy (naive) stamp itself is comparable too
    store._conn.execute("UPDATE agents SET updated_at=? WHERE agent_id=?", ("2026-01-01T00:00:00", "a1"))
    store._conn.commit()
    assert c.patch("/agents/a1", json={"status": "killed", "if_updated_at": "2026-01-01T00:00:00"}).status_code == 200
