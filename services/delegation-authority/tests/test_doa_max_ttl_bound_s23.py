"""Scout S-2-3: a roster row's `max_ttl_days` has an upper bound. `timedelta(days=n)` raises OverflowError above
999999999, and the mint compared `expires - now` against it outside any try, so one typo in the roster (an extra
digit, a value in seconds) turned every mint by that grantor into a 500. A roster that cannot be read as valid is a
503 before anything is written (the existing fail-closed rule), so the bound belongs on the row."""
from __future__ import annotations

import pytest
from test_doa_roster import Spine, write_manifest, write_roster

from delegation_authority.doa import DoaRosterError, load_roster

TIMEDELTA_MAX_DAYS = 999_999_999


@pytest.fixture()
def spine(tmp_path):
    return Spine(tmp_path, write_manifest(tmp_path))


@pytest.mark.parametrize("days", [TIMEDELTA_MAX_DAYS + 1, 10**12, 10**30])
def test_an_overflowing_max_ttl_days_is_refused_at_load(tmp_path, days):
    with pytest.raises(DoaRosterError):
        load_roster(write_roster(tmp_path, max_ttl_days=days))


@pytest.mark.parametrize("days", [TIMEDELTA_MAX_DAYS + 1, 10**12])
def test_a_mint_under_an_overflowing_roster_is_503_never_500(spine, tmp_path, monkeypatch, days):
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path, max_ttl_days=days)))
    r = spine.mint()
    assert r.status_code == 503, r.text
    assert spine.mint_events() == []          # refused before any ledger write


def test_the_largest_value_timedelta_takes_still_loads_and_mints(spine, tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_DOA_ROSTER", str(write_roster(tmp_path, max_ttl_days=TIMEDELTA_MAX_DAYS)))
    assert load_roster(write_roster(tmp_path, max_ttl_days=TIMEDELTA_MAX_DAYS)).grantors[0].max_ttl_days == TIMEDELTA_MAX_DAYS
    assert spine.mint().status_code == 201
