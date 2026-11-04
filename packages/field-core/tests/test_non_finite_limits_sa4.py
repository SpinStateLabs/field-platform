"""A spend cap or a token spend ceiling of Infinity is a cap that never trips, and it
does not survive JSON (pydantic writes `null`) (scout S-A4). NaN was already refused by
the `gt=0`/`ge=0` bound; Infinity passed it."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from field_core.delegation import DelegationToken
from field_core.manifest import FieldManifest, SpendCap
from field_core.templates_api import template_data

NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)
BAD = [float("inf"), float("-inf"), float("nan")]


def _token(**kw):
    return DelegationToken(token_id="t", agent_id="a", granted_by="o", scope=["x"],
                           issued_at=NOW, expires_at=NOW + timedelta(days=1), **kw)


@pytest.mark.parametrize("bad", BAD)
def test_spendcap_refuses_a_non_finite_limit(bad):
    with pytest.raises(ValidationError):
        SpendCap(currency="USD", limit=bad, period="day")


@pytest.mark.parametrize("ok", [0.01, 1, 500, 1e12])
def test_spendcap_keeps_a_finite_positive_limit(ok):
    assert SpendCap(currency="USD", limit=ok, period="day").limit == ok


@pytest.mark.parametrize("bad", [0, -1])
def test_spendcap_still_refuses_zero_and_negative(bad):
    with pytest.raises(ValidationError):
        SpendCap(currency="USD", limit=bad, period="day")


@pytest.mark.parametrize("bad", BAD)
def test_a_manifest_with_a_non_finite_spend_cap_is_refused(bad):
    data = copy.deepcopy(template_data("financial-agent"))
    data["enforcement"]["spend_cap"]["limit"] = bad
    with pytest.raises(ValidationError):
        FieldManifest.from_dict(data)


@pytest.mark.parametrize("bad", BAD)
def test_a_token_refuses_a_non_finite_max_spend(bad):
    with pytest.raises(ValidationError):
        _token(max_spend_usd=bad)


@pytest.mark.parametrize("ok", [None, 0, 0.0, 12.5, 1e9])
def test_a_token_keeps_none_zero_and_finite_max_spend(ok):
    assert _token(max_spend_usd=ok).max_spend_usd == ok
