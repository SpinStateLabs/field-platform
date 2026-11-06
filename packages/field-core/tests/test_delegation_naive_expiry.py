"""S6-3: ``DelegationToken.status()`` reads a naive ``expires_at`` (a row from an older build or written by hand) as UTC,
as delegation-authority's ``_epoch`` does, instead of raising ``TypeError`` out of ``/introspect``."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from field_core.delegation import DelegationToken, TokenStatus

NOW = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)


def token(expires, **kw):
    return DelegationToken(agent_id="a", granted_by="Controller", scope=["s"], issued_at=NOW - timedelta(days=1),
                           expires_at=expires, **kw)


@pytest.mark.parametrize("delta,status", [(timedelta(hours=1), TokenStatus.ACTIVE),
                                          (-timedelta(hours=1), TokenStatus.EXPIRED),
                                          (timedelta(0), TokenStatus.EXPIRED),
                                          (timedelta(seconds=1), TokenStatus.ACTIVE),
                                          (-timedelta(seconds=1), TokenStatus.EXPIRED)])
def test_a_naive_expiry_is_read_as_utc(delta, status):
    naive = (NOW + delta).replace(tzinfo=None)
    assert token(naive).status(NOW) is status


def test_naive_and_aware_expiries_agree():
    for delta in (timedelta(hours=1), -timedelta(hours=1), timedelta(0)):
        assert token((NOW + delta).replace(tzinfo=None)).status(NOW) is token(NOW + delta).status(NOW)


def test_revoked_wins_over_a_naive_expiry():
    t = token((NOW + timedelta(hours=1)).replace(tzinfo=None), revoked=True)
    assert t.status(NOW) is TokenStatus.REVOKED
    assert token((NOW - timedelta(hours=1)).replace(tzinfo=None), revoked=True).status(NOW) is TokenStatus.REVOKED


def test_a_naive_now_is_also_read_as_utc():
    assert token(NOW + timedelta(hours=1)).status(NOW.replace(tzinfo=None)) is TokenStatus.ACTIVE
    assert token(NOW - timedelta(hours=1)).status(NOW.replace(tzinfo=None)) is TokenStatus.EXPIRED


def test_a_non_utc_aware_expiry_is_compared_by_instant_not_by_wall_clock():
    plus5 = timezone(timedelta(hours=5))
    assert token(datetime(2026, 7, 15, 16, 0, tzinfo=plus5)).status(NOW) is TokenStatus.EXPIRED   # 11:00 UTC
    assert token(datetime(2026, 7, 15, 18, 0, tzinfo=plus5)).status(NOW) is TokenStatus.ACTIVE    # 13:00 UTC


def test_is_active_and_the_default_now_work_for_naive_values():
    far = (datetime.now(timezone.utc) + timedelta(days=30)).replace(tzinfo=None)
    assert token(far).is_active() and token(far).status() is TokenStatus.ACTIVE
    past = (datetime.now(timezone.utc) - timedelta(days=30)).replace(tzinfo=None)
    assert not token(past).is_active()


def test_the_serialised_value_is_not_changed():
    naive = (NOW + timedelta(hours=1)).replace(tzinfo=None)
    assert token(naive).expires_at.tzinfo is None
    assert token(naive).model_dump(mode="json")["expires_at"] == naive.isoformat()


def test_the_server_zone_does_not_move_a_naive_expiry(monkeypatch):
    """On a UTC machine reading a naive value as local time is invisible; run the check in a zone that is not UTC."""
    import time
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    time.tzset()
    try:
        assert token((NOW + timedelta(hours=1)).replace(tzinfo=None)).status(NOW) is TokenStatus.ACTIVE
        assert token((NOW - timedelta(hours=1)).replace(tzinfo=None)).status(NOW) is TokenStatus.EXPIRED
    finally:
        monkeypatch.undo()
        time.tzset()
