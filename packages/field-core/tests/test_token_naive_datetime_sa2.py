"""A DelegationToken refuses timezone-naive datetimes (scout S-A2). status() compares against
an aware `now`, so a naive value used to raise TypeError ("can't compare offset-naive and
offset-aware datetimes") at the first status() call. The fields are AwareDatetime now: a
naive value is a ValidationError at construction, NEVER assumed to be UTC.

(My first version of this fix coerced a naive value to UTC. CI caught the consequence:
tools/generate_doa_roster.py refuses naive token times BY POLICY and checks `tzinfo is
None` on the parsed model, so coercion silently defeated that refusal for delegation-of-
authority data. Refusing at the model matches the repo's rule and keeps that tool's guard
working; tools/tests/test_generate_doa_roster.py::test_malformed_tokens_input_is_refused
pins the tool side.)"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from field_core.delegation import DelegationToken, TokenStatus

UTC = timezone.utc
NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
NAIVE = datetime(2026, 6, 1, 13, 0, 0)


def _tok(**kw):
    base = dict(token_id="t", agent_id="a", granted_by="o", scope=["x"],
                issued_at=NOW - timedelta(hours=1), expires_at=NOW + timedelta(hours=1))
    base.update(kw)
    return DelegationToken(**base)


@pytest.mark.parametrize("field", ["issued_at", "expires_at"])
def test_a_naive_required_datetime_is_refused(field):
    with pytest.raises(ValidationError):
        _tok(**{field: NAIVE})


def test_a_naive_revoked_at_is_refused():
    with pytest.raises(ValidationError):
        _tok(revoked=True, revoked_at=NAIVE)


@pytest.mark.parametrize("text", ["2026-06-01T13:00:00", "2026-06-01 13:00:00", "2026-06-01T13:00:00.5"])
def test_a_naive_iso_string_from_json_is_refused(text):
    with pytest.raises(ValidationError):
        DelegationToken.model_validate({
            "token_id": "t", "agent_id": "a", "granted_by": "o", "scope": ["x"],
            "issued_at": "2026-06-01T11:00:00+00:00", "expires_at": text})


@pytest.mark.parametrize("text", ["2026-06-01T13:00:00+00:00", "2026-06-01T13:00:00Z", "2026-06-01T18:30:00+05:30"])
def test_an_iso_string_with_an_offset_is_accepted_and_status_works(text):
    t = DelegationToken.model_validate({
        "token_id": "t", "agent_id": "a", "granted_by": "o", "scope": ["x"],
        "issued_at": "2026-06-01T11:00:00+00:00", "expires_at": text})
    assert t.expires_at.tzinfo is not None
    assert t.status(NOW) is TokenStatus.ACTIVE and t.is_active(NOW) is True


def test_an_aware_datetime_keeps_its_own_offset():
    plus5 = timezone(timedelta(hours=5))
    exp = datetime(2026, 6, 1, 20, 0, tzinfo=plus5)           # = 15:00 UTC
    t = _tok(expires_at=exp)
    assert t.expires_at == exp and t.expires_at.utcoffset() == timedelta(hours=5)
    assert t.status(NOW) is TokenStatus.ACTIVE


def test_status_boundaries_are_unchanged_for_aware_values():
    assert _tok(expires_at=NOW).status(NOW) is TokenStatus.EXPIRED          # exactly now
    assert _tok(expires_at=NOW - timedelta(seconds=1)).status(NOW) is TokenStatus.EXPIRED
    assert _tok(expires_at=NOW + timedelta(seconds=1)).status(NOW) is TokenStatus.ACTIVE
    assert _tok(revoked=True).status(NOW) is TokenStatus.REVOKED


def test_revoke_returns_an_aware_revoked_at():
    r = _tok().revoke()
    assert r.revoked_at.tzinfo is not None and r.status(NOW) is TokenStatus.REVOKED


@pytest.mark.parametrize("field", ["issued_at", "expires_at"])
def test_a_missing_required_datetime_is_still_refused(field):
    data = dict(token_id="t", agent_id="a", granted_by="o", scope=["x"],
                issued_at=NOW, expires_at=NOW + timedelta(hours=1))
    del data[field]
    with pytest.raises(ValidationError):
        DelegationToken(**data)


def test_the_serialised_token_round_trips_with_its_offset():
    t = _tok()
    again = DelegationToken.model_validate_json(t.model_dump_json())
    assert again == t and again.expires_at.tzinfo is not None
