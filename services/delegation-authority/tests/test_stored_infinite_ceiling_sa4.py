"""S-A4 follow-up (review C1 on PR 502): a token stored with an INFINITE spend ceiling, as the code before the DelegationToken
bound could write one (a roster row ``max_spend_usd: .inf`` meaning "no cap"), must not take reads down. The ceiling lives in
a REAL side table that holds +inf, and DelegationToken is rebuilt from the database on every read, so without a read-side rule
one such row made /health, GET /tokens and GET /tokens?agent_id= answer 500."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from delegation_authority.api import create_app
from delegation_authority.store import TokenStore
from field_core.delegation import DelegationToken

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _token(agent, ceiling=None):
    return DelegationToken(agent_id=agent, granted_by="don", scope=["s"], issued_at=NOW,
                           expires_at=NOW + timedelta(days=1), max_spend_usd=ceiling)


def _store_with_infinite(tmp_path, value=float("inf")):
    store = TokenStore(tmp_path / "tokens.sqlite3")
    bad = store.save(_token("bad-agent"))
    good = store.save(_token("good-agent", 25.5))
    other = store.save(_token("other-agent"))
    conn = sqlite3.connect(str(tmp_path / "tokens.sqlite3"))
    conn.execute("INSERT INTO token_spend_ceilings VALUES (?,?)", (bad.token_id, value))
    conn.commit()
    conn.close()
    return TokenStore(tmp_path / "tokens.sqlite3"), bad, good, other


@pytest.mark.parametrize("value", [float("inf"), float("-inf")], ids=["plus-inf", "minus-inf"])
def test_a_stored_infinite_ceiling_reads_as_no_ceiling_and_breaks_nothing(tmp_path, value):
    store, bad, good, other = _store_with_infinite(tmp_path, value)
    assert store.get(bad.token_id).max_spend_usd is None
    assert store.get(good.token_id).max_spend_usd == 25.5            # a finite ceiling is untouched
    assert store.get(other.token_id).max_spend_usd is None
    assert len(store.list()) == 3


def test_health_and_the_token_listings_answer_200_with_such_a_row(tmp_path):
    store, bad, good, _ = _store_with_infinite(tmp_path)
    client = TestClient(create_app(store=store))
    assert client.get("/health").status_code == 200 and client.get("/health").json()["token_count"] == 3
    assert client.get("/tokens").status_code == 200
    r = client.get("/tokens", params={"agent_id": "bad-agent"})
    assert r.status_code == 200 and [t["agent_id"] for t in r.json()] == ["bad-agent"]
    assert sorted(t["agent_id"] for t in client.get("/tokens").json()) == ["bad-agent", "good-agent", "other-agent"]
    assert {t.agent_id: t.max_spend_usd for t in store.list()} == {"bad-agent": None, "good-agent": 25.5, "other-agent": None}


def test_saving_again_over_such_a_row_returns_no_ceiling_not_infinity(tmp_path):
    store, bad, _, _ = _store_with_infinite(tmp_path)
    revoked = bad.model_copy(update={"revoked": True, "revocation_id": "r1", "revoked_at": NOW})
    saved = store.save(revoked)                                        # a later save (revoke) reads the stored ceiling back
    assert saved.max_spend_usd is None


def test_a_finite_ceiling_still_round_trips_exactly(tmp_path):
    store = TokenStore(tmp_path / "tokens.sqlite3")
    t = store.save(_token("a", 1e12))
    assert store.get(t.token_id).max_spend_usd == 1e12
    assert store.save(_token("b", 0.0)).max_spend_usd == 0.0
