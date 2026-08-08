"""delegation-authority tests: full-spine wiring, adversarial expiry/revocation,
fail-closed behavior when the ledger is down."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.clients import LedgerClient, RegistryClient
from delegation_authority.store import TokenStore
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore


class DownClient:
    """Stub http client that always fails — simulates an unreachable service."""

    def post(self, *a, **k):
        raise ConnectionError("service down")

    def get(self, *a, **k):
        raise ConnectionError("service down")


@pytest.fixture()
def ledger_store(tmp_path):
    return LedgerStore(tmp_path / "events.jsonl")


@pytest.fixture()
def spine(tmp_path, ledger_store):
    """Registry + ledger + delegation wired in-process, exactly as in prod."""
    registry_client = TestClient(
        create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3"))
    )
    ledger_client = TestClient(create_ledger_app(store=ledger_store))
    delegation = TestClient(
        create_delegation_app(
            store=TokenStore(tmp_path / "tokens.sqlite3"),
            ledger=LedgerClient(client=ledger_client, base_url="http://testserver"),
            registry=RegistryClient(
                client=registry_client, base_url="http://testserver"
            ),
        )
    )
    registry_client.post(
        "/agents",
        json={
            "agent_id": "invoicing-agent",
            "name": "Invoice Drafting Copilot",
            "owner": "Controller, Spin State Labs",
            "domain": "finance",
        },
    )
    return delegation, registry_client, ledger_client


def mint(delegation, **overrides):
    body = {
        "agent_id": "invoicing-agent",
        "granted_by": "Controller, Spin State Labs",
        "scope": ["read timesheets", "draft invoices"],
        "ttl_seconds": 3600,
    }
    body.update(overrides)
    return delegation.post("/tokens", json=body)


def test_mint_writes_ledger_and_persists(spine):
    delegation, _, ledger_client = spine
    r = mint(delegation)
    assert r.status_code == 201
    token = r.json()
    assert token["revoked"] is False

    events = ledger_client.get("/events", params={"event_type": "delegation.mint"}).json()
    assert len(events) == 1
    assert events[0]["agent_id"] == "invoicing-agent"
    assert events[0]["payload"]["token_id"] == token["token_id"]

    introspection = delegation.post(
        "/introspect", json={"token_id": token["token_id"]}
    ).json()
    assert introspection["active"] is True
    assert introspection["status"] == "active"


def test_mint_refused_for_unregistered_agent(spine):
    delegation, _, ledger_client = spine
    r = mint(delegation, agent_id="ghost-agent")
    assert r.status_code == 404
    assert ledger_client.get("/events").json() == []  # nothing minted, nothing logged


def test_mint_refused_for_killed_agent(spine):
    delegation, registry_client, _ = spine
    registry_client.patch("/agents/invoicing-agent", json={"status": "killed"})
    r = mint(delegation)
    assert r.status_code == 409


def test_adversarial_expired_token_fails_introspection(spine):
    delegation, _, _ = spine
    r = mint(
        delegation,
        ttl_seconds=None,
        expires_at=(datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
    )
    token_id = r.json()["token_id"]

    import time

    time.sleep(1.2)
    introspection = delegation.post("/introspect", json={"token_id": token_id}).json()
    assert introspection["active"] is False
    assert introspection["status"] == "expired"


def test_adversarial_revoked_token_fails_introspection(spine):
    delegation, _, ledger_client = spine
    token_id = mint(delegation).json()["token_id"]

    r = delegation.post(f"/tokens/{token_id}/revoke")
    assert r.status_code == 200
    assert r.json()["revoked"] is True

    introspection = delegation.post("/introspect", json={"token_id": token_id}).json()
    assert introspection["active"] is False
    assert introspection["status"] == "revoked"

    revokes = ledger_client.get(
        "/events", params={"event_type": "delegation.revoke"}
    ).json()
    assert len(revokes) == 1

    # Idempotent: second revoke returns the same token, no duplicate event.
    delegation.post(f"/tokens/{token_id}/revoke")
    revokes = ledger_client.get(
        "/events", params={"event_type": "delegation.revoke"}
    ).json()
    assert len(revokes) == 1


def test_adversarial_unknown_token_fails_closed(spine):
    delegation, _, _ = spine
    introspection = delegation.post(
        "/introspect", json={"token_id": "no-such-token"}
    ).json()
    assert introspection["active"] is False
    assert "fail closed" in introspection["reason"]


def test_adversarial_ledger_down_mint_fails_closed(tmp_path):
    """Authority that cannot be audited must not exist."""
    registry_client = TestClient(
        create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3"))
    )
    registry_client.post(
        "/agents",
        json={"agent_id": "invoicing-agent", "name": "Inv", "owner": "Controller"},
    )
    delegation = TestClient(
        create_delegation_app(
            store=TokenStore(tmp_path / "tokens.sqlite3"),
            ledger=LedgerClient(client=DownClient(), base_url="http://testserver"),
            registry=RegistryClient(
                client=registry_client, base_url="http://testserver"
            ),
        )
    )
    r = mint(delegation)
    assert r.status_code == 502
    assert "refusing to mint" in r.json()["detail"]
    assert delegation.get("/tokens").json() == []  # no token persisted


def test_mint_requires_exactly_one_expiry(spine):
    delegation, _, _ = spine
    assert mint(delegation, ttl_seconds=None).status_code == 422
    assert (
        mint(
            delegation,
            expires_at=(datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
        ).status_code
        == 422
    )
