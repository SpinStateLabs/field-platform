"""S7-18 — GET /health counts tokens with one COUNT, not by decoding every row."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from delegation_authority.api import create_app
from delegation_authority.store import TokenStore
from field_core.delegation import DelegationToken

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _token(i: int) -> DelegationToken:
    return DelegationToken(agent_id=f"a{i}", granted_by="don", scope=["s"],
                           issued_at=NOW, expires_at=NOW + timedelta(days=1))


@pytest.fixture()
def store(tmp_path):
    return TokenStore(tmp_path / "tokens.sqlite3")


def test_count_is_zero_on_an_empty_store(store):
    assert store.count() == 0


def test_count_equals_len_list_after_mints_and_a_revoke(store):
    saved = [store.save(_token(i)) for i in range(4)]
    assert store.count() == len(store.list()) == 4
    revoked = saved[0].model_copy(update={"revoked": True, "revocation_id": "r1", "revoked_at": NOW})
    store.save_revoked(revoked)
    assert store.count() == len(store.list()) == 4  # revoked tokens still count


def test_health_does_not_decode_the_rows(store, monkeypatch):
    for i in range(3):
        store.save(_token(i))

    def boom(*a, **k):
        raise AssertionError("health() must not call TokenStore.list")

    monkeypatch.setattr(TokenStore, "list", boom)
    r = TestClient(create_app(store=store)).get("/health")
    assert r.status_code == 200
    assert r.json()["token_count"] == 3
    assert isinstance(r.json()["token_count"], int)


def test_the_count_is_per_token_not_per_agent_or_per_grantor(store):
    """Review finding 1 (M6, M17): two tokens for one agent, and tokens from different grantors, all count."""
    def tok(agent, grantor, scope):
        return DelegationToken(agent_id=agent, granted_by=grantor, scope=[scope],
                               issued_at=NOW, expires_at=NOW + timedelta(days=1))
    store.save(tok("same-agent", "don", "s1"))
    store.save(tok("same-agent", "don", "s2"))          # a second token for the same agent
    store.save(tok("other-agent", "don-admin", "s1"))   # another grantor
    store.save(tok("third-agent", "someone-else", "s3"))
    assert store.count() == len(store.list()) == 4
    health = TestClient(create_app(store=store)).get("/health").json()
    assert health["token_count"] == 4
