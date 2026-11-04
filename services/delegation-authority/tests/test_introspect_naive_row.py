"""S6-3: a token row holding NAIVE ``issued_at``/``expires_at`` (older build, or written by hand) introspects, lists and
reports ``exp`` in UTC; it was a ``TypeError`` -> 500 out of ``token.status()``."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from delegation_authority.api import create_app
from delegation_authority.store import TokenStore
from field_core.delegation import DelegationToken


@pytest.fixture()
def rig(tmp_path):
    store = TokenStore(tmp_path / "t.sqlite3")
    return TestClient(create_app(store=store)), store


def naive_token(hours, token_id, **kw):
    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    return DelegationToken(token_id=token_id, agent_id="a", granted_by="Controller", scope=["read timesheets"],
                           issued_at=now - timedelta(days=1), expires_at=now + timedelta(hours=hours), **kw)


def test_the_stored_row_really_is_naive(rig):
    _, store = rig
    store.save(naive_token(1, "t1"))
    assert store.get("t1").expires_at.tzinfo is None


def test_introspect_a_naive_row_ahead_is_active(rig):
    client, store = rig
    store.save(naive_token(1, "t1"))
    r = client.post("/introspect", json={"token_id": "t1"})
    assert r.status_code == 200, r.text
    assert r.json()["active"] is True and r.json()["status"] == "active"


def test_introspect_a_naive_row_behind_is_expired(rig):
    client, store = rig
    store.save(naive_token(-1, "t1"))
    r = client.post("/introspect", json={"token_id": "t1"})
    assert r.status_code == 200 and r.json()["active"] is False and r.json()["status"] == "expired"


def test_a_revoked_naive_row_is_revoked(rig):
    client, store = rig
    store.save(naive_token(1, "t1", revoked=True, revocation_id="r1"))
    r = client.post("/introspect", json={"token_id": "t1"})
    assert r.status_code == 200 and r.json()["status"] == "revoked"


def test_tokens_still_lists_a_naive_row(rig):
    client, store = rig
    store.save(naive_token(1, "t1"))
    r = client.get("/tokens")
    assert r.status_code == 200 and [t["token_id"] for t in r.json()] == ["t1"]


def test_oauth_introspect_exp_is_the_utc_epoch(rig):
    client, store = rig
    t = naive_token(1, "t1")
    store.save(t)
    r = client.post("/oauth/introspect", content="token=t1", headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] is True
    assert body["exp"] == int(t.expires_at.replace(tzinfo=timezone.utc).timestamp())
    assert body["iat"] == int(t.issued_at.replace(tzinfo=timezone.utc).timestamp())


def test_oauth_introspect_a_naive_expired_row_is_inactive(rig):
    client, store = rig
    store.save(naive_token(-1, "t1"))
    r = client.post("/oauth/introspect", content="token=t1", headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 200 and r.json() == {"active": False}
