"""B2 — RFC 7662-shaped introspection at POST /oauth/introspect.

Two properties are security-critical and each has a test that fails if the
guard is weakened:
* an inactive token's response is EXACTLY {"active": false} — no status, no
  reason, no agent id. A leak here tells an attacker whether a token id ever
  existed and why it stopped working.
* the body is form-urlencoded and parsed by hand. Declaring a FastAPI
  `Form()` parameter would need python-multipart, which is not installed:
  `create_app()` would raise at route registration and take seven other
  suites down with it.
  `test_create_app_registers_the_route_without_a_form_dependency` pins that.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.clients import LedgerClient, RegistryClient
from delegation_authority.store import TokenStore
from field_core.delegation import DelegationToken
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

AGENT_ID = "invoicing-agent"
SCOPE = ["read timesheets", "draft invoices"]
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


@pytest.fixture()
def spine(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_DOA_ROSTER", raising=False)
    store = TokenStore(tmp_path / "tokens.sqlite3")
    registry = TestClient(
        create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3"))
    )
    ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
    delegation = TestClient(
        create_delegation_app(
            store=store,
            ledger=LedgerClient(client=ledger, base_url="http://t"),
            registry=RegistryClient(client=registry, base_url="http://t"),
        )
    )
    registry.post(
        "/agents",
        json={
            "agent_id": AGENT_ID,
            "name": "Invoice Drafting Copilot",
            "owner": "Controller, Spin State Labs",
            "domain": "finance",
        },
    )
    return delegation, store


def mint(delegation, **overrides):
    body = {
        "agent_id": AGENT_ID,
        "granted_by": "Controller, Spin State Labs",
        "scope": list(SCOPE),
        "ttl_seconds": 3600,
    }
    body.update(overrides)
    r = delegation.post("/tokens", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def oauth(delegation, body):
    return delegation.post("/oauth/introspect", content=body, headers=FORM)


def test_active_token_exact_key_set_and_types(spine):
    delegation, _ = spine
    token = mint(delegation)
    r = oauth(delegation, f"token={token['token_id']}")
    assert r.status_code == 200
    body = r.json()

    assert set(body) == {
        "active",
        "scope",
        "scope_list",
        "exp",
        "iat",
        "sub",
        "client_id",
        "token_type",
    }
    assert body["active"] is True
    assert isinstance(body["scope"], str)
    assert isinstance(body["scope_list"], list)
    assert isinstance(body["exp"], int) and isinstance(body["iat"], int)
    assert isinstance(body["sub"], str) and isinstance(body["client_id"], str)
    assert body["token_type"] == "opaque"


def test_scope_is_rfc_string_and_scope_list_keeps_the_spaces(spine):
    """FIELD scopes contain spaces, so the RFC's space-delimited `scope`
    cannot be split back into them — `scope_list` is why the response is
    usable at all."""
    delegation, _ = spine
    token = mint(delegation)
    body = oauth(delegation, f"token={token['token_id']}").json()
    assert body["scope"] == "read timesheets draft invoices"
    assert body["scope_list"] == SCOPE
    assert body["scope"].split(" ") != body["scope_list"]


def test_exp_iat_sub_and_client_id(spine):
    delegation, _ = spine
    token = mint(delegation)
    body = oauth(delegation, f"token={token['token_id']}").json()
    expires_at = datetime.fromisoformat(token["expires_at"])
    issued_at = datetime.fromisoformat(token["issued_at"])
    assert body["exp"] == int(expires_at.timestamp())
    assert body["iat"] == int(issued_at.timestamp())
    assert body["sub"] == body["client_id"] == AGENT_ID


def test_revoked_token_returns_only_active_false(spine):
    delegation, _ = spine
    token = mint(delegation)
    assert delegation.post(f"/tokens/{token['token_id']}/revoke").status_code == 200
    r = oauth(delegation, f"token={token['token_id']}")
    assert r.status_code == 200
    assert r.json() == {"active": False}


def test_expired_token_returns_only_active_false(spine):
    """Expiry is forced through the store rather than a real sleep (repo rule:
    frozen clocks, never sleeps); the mint endpoint refuses a past expiry."""
    delegation, store = spine
    now = datetime.now(timezone.utc)
    store.save(
        DelegationToken(
            token_id="expired-token",
            agent_id=AGENT_ID,
            granted_by="Controller, Spin State Labs",
            scope=list(SCOPE),
            issued_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )
    )
    r = oauth(delegation, "token=expired-token")
    assert r.status_code == 200
    assert r.json() == {"active": False}


def test_unknown_token_returns_only_active_false(spine):
    delegation, _ = spine
    r = oauth(delegation, "token=no-such-token-id")
    assert r.status_code == 200
    assert r.json() == {"active": False}


def test_inactive_responses_leak_no_reason(spine):
    """One assertion for all three inactive cases: an attacker must not be
    able to tell 'revoked' from 'expired' from 'never existed'."""
    delegation, store = spine
    now = datetime.now(timezone.utc)
    revoked = mint(delegation)
    delegation.post(f"/tokens/{revoked['token_id']}/revoke")
    store.save(
        DelegationToken(
            token_id="stale",
            agent_id=AGENT_ID,
            granted_by="Controller, Spin State Labs",
            scope=list(SCOPE),
            issued_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),
        )
    )
    bodies = [
        oauth(delegation, f"token={revoked['token_id']}").json(),
        oauth(delegation, "token=stale").json(),
        oauth(delegation, "token=never-existed").json(),
    ]
    assert bodies == [{"active": False}] * 3


def test_missing_token_field_is_400(spine):
    delegation, _ = spine
    assert oauth(delegation, "").status_code == 400
    assert oauth(delegation, "token=").status_code == 400
    assert oauth(delegation, "token=%20%20").status_code == 400
    assert oauth(delegation, "tokenid=abc").status_code == 400


def test_json_body_is_4xx(spine):
    """A JSON body carries no form `token` field — refused, never guessed at."""
    delegation, _ = spine
    r = delegation.post("/oauth/introspect", json={"token": "abc"})
    assert 400 <= r.status_code < 500


def test_bespoke_introspect_endpoint_is_untouched(spine):
    """The sentinel and the CLI depend on /introspect's own shape."""
    delegation, _ = spine
    token = mint(delegation)
    body = delegation.post(
        "/introspect", json={"token_id": token["token_id"]}
    ).json()
    assert body["token_id"] == token["token_id"]
    assert body["status"] == "active"
    assert body["scope"] == SCOPE


def test_create_app_registers_the_route_without_a_form_dependency(tmp_path):
    """Route registration must not need python-multipart: a `Form()` parameter
    makes create_app() raise at import-time registration, which would take
    down every other suite that builds this app. Building it here, in a test
    that only registers routes, is the regression guard."""
    app = create_delegation_app(store=TokenStore(tmp_path / "t.sqlite3"))
    paths = {route.path for route in app.routes}
    assert "/oauth/introspect" in paths
    assert "/introspect" in paths


def test_oauth_introspect_is_protected_by_the_shared_secret(spine, monkeypatch):
    """The new route must not be an unauthenticated hole in the perimeter."""
    delegation, _ = spine
    token = mint(delegation)
    monkeypatch.setenv("FIELD_SHARED_SECRET", "s3cret")
    assert oauth(delegation, f"token={token['token_id']}").status_code == 401
    r = delegation.post(
        "/oauth/introspect",
        content=f"token={token['token_id']}",
        headers={**FORM, "x-field-auth": "s3cret"},
    )
    assert r.status_code == 200
    assert r.json()["active"] is True
