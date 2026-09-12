"""Delegation token + conformance verdict tests, incl. adversarial cases."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from field_core.conformance import CLAUSES, ConformanceVerdict, Decision
from field_core.delegation import DelegationToken, TokenStatus

NOW = datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)


def make_token(**overrides) -> DelegationToken:
    base = dict(
        agent_id="invoicing-agent",
        granted_by="Controller, Spin State Labs",
        scope=["read timesheets", "draft invoices"],
        issued_at=NOW - timedelta(days=1),
        expires_at=NOW + timedelta(days=30),
    )
    base.update(overrides)
    return DelegationToken(**base)


def test_active_token():
    token = make_token()
    assert token.status(NOW) is TokenStatus.ACTIVE
    assert token.is_active(NOW)
    assert token.covers("draft invoices")
    assert not token.covers("send invoices")


def test_adversarial_expired_token_inactive():
    token = make_token(expires_at=NOW - timedelta(seconds=1))
    assert token.status(NOW) is TokenStatus.EXPIRED
    assert not token.is_active(NOW)


def test_adversarial_revoked_token_inactive_even_if_unexpired():
    token = make_token().revoke(now=NOW)
    assert token.status(NOW) is TokenStatus.REVOKED
    assert not token.is_active(NOW)
    assert token.revocation_id is not None
    assert token.revoked_at == NOW


def test_revocation_wins_over_expiry():
    token = make_token(expires_at=NOW - timedelta(days=1)).revoke(now=NOW)
    assert token.status(NOW) is TokenStatus.REVOKED


def test_empty_scope_rejected():
    with pytest.raises(ValidationError):
        make_token(scope=[])


def test_verdict_allow():
    v = ConformanceVerdict(
        decision=Decision.ALLOW, agent_id="a", action="read timesheets"
    )
    assert v.allowed
    assert v.clause_text() is None


def test_verdict_block_carries_clause():
    v = ConformanceVerdict(
        decision=Decision.BLOCK,
        agent_id="a",
        action="wire funds",
        clause_id="D.scope",
        reasons=["'wire funds' not in delegated scope"],
    )
    assert not v.allowed
    assert v.clause_text() == CLAUSES["D.scope"]


def test_clause_registry_covers_all_letters():
    prefixes = {c.split(".")[0] for c in CLAUSES}
    assert {"F", "I", "E", "L", "D"} <= prefixes


def test_clause_registry_carries_d_grantor():
    """B1: the DOA roster refusal cites a clause id, so incident-replay can
    point at the rule that fired. Delete this clause and delegation-authority's
    403s become uncitable."""
    assert "D.grantor" in CLAUSES
    v = ConformanceVerdict(
        decision=Decision.BLOCK,
        agent_id="invoicing-agent",
        action="mint delegation token",
        clause_id="D.grantor",
        reasons=["grantor 'Someone Else' is not on the DOA roster"],
    )
    assert not v.allowed
    assert v.clause_text() == CLAUSES["D.grantor"]
    assert "roster" in CLAUSES["D.grantor"]
