"""A DelegationToken built from timezone-naive datetimes must not make status() raise
TypeError ("can't compare offset-naive and offset-aware datetimes") (scout S-A2).
The mint route already treats a naive expires_at as UTC (delegation-authority api.py);
the model now does the same for every datetime field, so any caller is consistent."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from field_core.delegation import DelegationToken, TokenStatus

UTC = timezone.utc
NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)


def _tok(**kw):
    base = dict(token_id="t", agent_id="a", granted_by="o", scope=["x"],
                issued_at=NOW - timedelta(hours=1), expires_at=NOW + timedelta(hours=1))
    base.update(kw)
    return DelegationToken(**base)


def test_naive_datetimes_are_read_as_utc_and_status_does_not_raise():
    t = _tok(issued_at=datetime(2026, 6, 1, 11, 0), expires_at=datetime(2026, 6, 1, 13, 0))
    assert t.issued_at.tzinfo is not None and t.expires_at.tzinfo is not None
    assert t.expires_at == datetime(2026, 6, 1, 13, 0, tzinfo=UTC)
    assert t.status(NOW) is TokenStatus.ACTIVE
    assert t.is_active(NOW) is True


def test_a_naive_expiry_in_the_past_is_expired_not_a_crash():
    t = _tok(expires_at=datetime(2026, 6, 1, 11, 59, 59))
    assert t.status(NOW) is TokenStatus.EXPIRED


def test_the_expiry_boundary_is_unchanged_at_exactly_now():
    assert _tok(expires_at=datetime(2026, 6, 1, 12, 0, 0)).status(NOW) is TokenStatus.EXPIRED


def test_a_naive_revoked_at_is_read_as_utc():
    t = _tok(revoked=True, revoked_at=datetime(2026, 6, 1, 11, 30))
    assert t.revoked_at == datetime(2026, 6, 1, 11, 30, tzinfo=UTC)
    assert t.status(NOW) is TokenStatus.REVOKED


def test_an_aware_datetime_keeps_its_own_offset():
    plus5 = timezone(timedelta(hours=5))
    exp = datetime(2026, 6, 1, 20, 0, tzinfo=plus5)           # = 15:00 UTC
    t = _tok(expires_at=exp)
    assert t.expires_at == exp and t.expires_at.utcoffset() == timedelta(hours=5)
    assert t.status(NOW) is TokenStatus.ACTIVE


def test_naive_iso_strings_from_json_are_read_as_utc():
    t = DelegationToken.model_validate({
        "token_id": "t", "agent_id": "a", "granted_by": "o", "scope": ["x"],
        "issued_at": "2026-06-01T11:00:00", "expires_at": "2026-06-01T13:00:00"})
    assert t.expires_at.tzinfo is not None and t.status(NOW) is TokenStatus.ACTIVE


def test_revoke_returns_an_aware_revoked_at():
    r = _tok().revoke()
    assert r.revoked_at.tzinfo is not None and r.status(NOW) is TokenStatus.REVOKED


@pytest.mark.parametrize("field", ["issued_at", "expires_at"])
def test_a_missing_required_datetime_is_still_refused(field):
    from pydantic import ValidationError

    data = dict(token_id="t", agent_id="a", granted_by="o", scope=["x"],
                issued_at=NOW, expires_at=NOW + timedelta(hours=1))
    del data[field]
    with pytest.raises(ValidationError):
        DelegationToken(**data)
