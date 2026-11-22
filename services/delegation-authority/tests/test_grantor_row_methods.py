"""S10-15: unit tests on `GrantorRow.may_delegate`, `GrantorRow.ledger_row` and `DoaRoster.find`, built directly, no app.

Before this file `may_delegate` and `ledger_row` were seen only through a whole mint (tests/test_doa_roster.py, tests/test_d1e_token_ceiling.py),
which pin the VALUES of a mint's `doa_row`, not the method's key set or the scope comparison rules. The `doa_row` payload keys are read by the D1e
ceiling and the incident replay, so a renamed, dropped or added key must fail here, at the source."""
from __future__ import annotations

import pytest

from delegation_authority.doa import DoaRoster, GrantorRow


def row(scopes=("read-timesheets", "write-invoices"), *, grantor="Don H", ttl=30, spend=None, active=True):
    return GrantorRow(grantor=grantor, allowed_scope=list(scopes), max_ttl_days=ttl, max_spend_usd=spend, active=active)


# -- may_delegate --------------------------------------------------------------------------------------------------------

def test_an_allowed_request_returns_nothing_and_so_does_an_empty_request():
    assert row().may_delegate(["read-timesheets"]) == []
    assert row().may_delegate(["write-invoices", "read-timesheets"]) == []
    assert row().may_delegate([]) == []


def test_the_refused_scopes_come_back_in_request_order():
    assert row().may_delegate(["z-last", "read-timesheets", "a-first", "m-mid"]) == ["z-last", "a-first", "m-mid"]


def test_duplicates_in_the_request_are_kept_not_collapsed():
    assert row().may_delegate(["nope", "read-timesheets", "nope", "nope"]) == ["nope", "nope", "nope"]


@pytest.mark.parametrize("variant", ["Read-Timesheets", "READ-TIMESHEETS", " read-timesheets", "read-timesheets ", "read-timesheets\n",
                                     "read\u2011timesheets"], ids=["title", "upper", "lead-pad", "trail-pad", "newline", "nb-hyphen"])
def test_a_case_or_whitespace_variant_is_not_allowed_exact_strings_only(variant):
    assert row().may_delegate([variant]) == [variant]


def test_a_scope_with_a_space_is_compared_whole_not_split():
    spaced = row(("read timesheets",))
    assert spaced.may_delegate(["read timesheets"]) == []
    assert spaced.may_delegate(["read"]) == ["read"]
    assert spaced.may_delegate(["timesheets"]) == ["timesheets"]
    assert spaced.may_delegate(["read timesheets extra"]) == ["read timesheets extra"]
    # and the other way round: a row allowing the parts does not allow the joined string
    assert row(("read", "timesheets")).may_delegate(["read timesheets"]) == ["read timesheets"]


def test_the_caller_list_is_not_modified():
    asked = ["x", "read-timesheets", "x"]
    row().may_delegate(asked)
    assert asked == ["x", "read-timesheets", "x"]


# -- ledger_row ----------------------------------------------------------------------------------------------------------

def test_ledger_row_is_exactly_grantor_max_ttl_days_and_max_spend_usd():
    got = row(grantor="Don H", ttl=45, spend=1250.5).ledger_row()
    assert got == {"grantor": "Don H", "max_ttl_days": 45, "max_spend_usd": 1250.5}
    assert list(got) == ["grantor", "max_ttl_days", "max_spend_usd"]


def test_an_unset_spend_ceiling_is_a_null_never_an_omitted_key():
    got = row(spend=None).ledger_row()
    assert "max_spend_usd" in got and got["max_spend_usd"] is None


def test_a_zero_spend_ceiling_stays_zero_not_null():
    assert row(spend=0).ledger_row()["max_spend_usd"] == 0


def test_ledger_row_never_carries_the_scope_list_or_the_active_flag():
    got = row(("secret-scope",), active=False).ledger_row()
    assert "allowed_scope" not in got and "active" not in got
    assert "secret-scope" not in repr(got)


# -- DoaRoster.find ------------------------------------------------------------------------------------------------------

def test_find_returns_a_retired_row_the_route_refuses_it_find_does_not():
    retired = row(grantor="Old Grantor", active=False)
    roster = DoaRoster(grantors=[row(), retired])
    found = roster.find("Old Grantor")
    assert found is retired and found.active is False


def test_find_is_exact_and_a_miss_is_none():
    roster = DoaRoster(grantors=[row(grantor="Don H")])
    assert roster.find("Don H") is not None
    for near in ("don h", "Don H ", " Don H", "Don  H", ""):
        assert roster.find(near) is None, repr(near)
    assert DoaRoster().find("Don H") is None
