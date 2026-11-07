"""C-625 (reviewer C-527 F-C527-2, F-C527-3): the expiry boundary and `covers` of the delegation token, pinned."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from field_core.delegation import DelegationToken, TokenStatus

T0 = datetime(2026, 10, 28, 12, 0, 0, tzinfo=timezone.utc)


def token(scope=("read timesheets",), **kw):
    return DelegationToken(token_id="t", agent_id="a", granted_by="g", scope=list(scope), issued_at=T0 - timedelta(hours=1),
                           expires_at=T0, **kw)


# --- F-C527-2: a token is dead AT the instant of expiry ---------------------------------------------------------------


def test_a_token_is_expired_at_exactly_its_expiry_instant():
    assert token().status(now=T0) is TokenStatus.EXPIRED
    assert token().is_active(now=T0) is False


def test_a_token_is_active_one_microsecond_before_its_expiry_and_expired_one_after():
    assert token().status(now=T0 - timedelta(microseconds=1)) is TokenStatus.ACTIVE
    assert token().status(now=T0 + timedelta(microseconds=1)) is TokenStatus.EXPIRED


def test_revocation_wins_over_expiry_at_and_after_the_boundary():
    revoked = token().revoke(now=T0)
    assert revoked.status(now=T0) is TokenStatus.REVOKED and revoked.status(now=T0 + timedelta(days=1)) is TokenStatus.REVOKED


def test_a_revoked_token_before_expiry_is_revoked_not_active():
    assert token().revoke().status(now=T0 - timedelta(minutes=5)) is TokenStatus.REVOKED


# --- F-C527-3: `covers` is an exact match -----------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["read timesheets", ])
def test_an_action_equal_to_a_scope_entry_is_covered(action):
    assert token().covers(action) is True


@pytest.mark.parametrize("action", [
    "read", "read time", "read timesheets ", " read timesheets", "READ TIMESHEETS", "read timesheets now",
    "read timesheetsX", "", "r", "timesheets",
])
def test_an_action_that_is_a_prefix_a_suffix_a_case_or_a_padding_of_a_scope_entry_is_not_covered(action):
    assert token().covers(action) is False


def test_a_scope_entry_that_is_a_prefix_of_the_action_does_not_cover_it():
    """startswith in the wrong direction: the scope `read` must not cover `read timesheets`."""
    assert token(scope=["read"]).covers("read timesheets") is False
    assert token(scope=["read timesheets"]).covers("read") is False


def test_covers_checks_every_entry():
    wide = token(scope=["draft invoices", "read timesheets", "send mail"])
    assert wide.covers("send mail") and wide.covers("draft invoices") and not wide.covers("send")
    assert not wide.covers("") and not wide.covers("send mail draft invoices")
