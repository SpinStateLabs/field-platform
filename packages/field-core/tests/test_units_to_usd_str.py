"""`units_to_usd_str`: a display helper for money; a unit is 1e-7 USD (scout P-5).

Before: below one cent it rendered `f"{units / USD_UNITS:.6f}"`, which has six decimals for a seven-decimal unit: 1 unit
showed as "$0", 5 units as "$0.000001" (rounded up), 99_999 units (just under a cent) as "$0.01" (rounded up to a whole
cent). Now every unit shows, with exact integer arithmetic. The one-cent-and-over branch (floored to whole cents) is
unchanged. Display only: nothing here is used in a cap comparison (pricing.py)."""

from __future__ import annotations

import pytest

from field_core.pricing import CENT_UNITS, USD_UNITS, units_to_usd_str


@pytest.mark.parametrize("units,expected", [
    (0, "$0"),
    (1, "$0.0000001"),
    (5, "$0.0000005"),
    (10, "$0.000001"),
    (99_999, "$0.0099999"),
    (50_000, "$0.005"),
    (CENT_UNITS - 1, "$0.0099999"),
])
def test_below_one_cent_shows_every_unit(units, expected):
    assert units_to_usd_str(units) == expected


@pytest.mark.parametrize("units,expected", [
    (CENT_UNITS, "$0.01"),
    (1_999_999, "$0.19"),            # floored to whole cents, as before
    (2_000_000, "$0.20"),
    (USD_UNITS, "$1.00"),
    (USD_UNITS * 3 + 1_500_000, "$3.15"),
])
def test_one_cent_and_over_is_floored_to_whole_cents_unchanged(units, expected):
    assert units_to_usd_str(units) == expected


@pytest.mark.parametrize("units,expected", [
    (-1, "$-0.0000001"),
    (-5, "$-0.0000005"),
    (-2_000_000, "$-0.2"),
])
def test_a_negative_amount_keeps_its_sign_and_every_unit(units, expected):
    assert units_to_usd_str(units) == expected


def test_a_sub_cent_amount_is_never_shown_as_a_whole_cent():
    assert units_to_usd_str(CENT_UNITS - 1) != "$0.01"


def test_the_sub_cent_text_parses_back_to_the_exact_unit_count():
    for units in (1, 7, 123, 99_999):
        assert round(float(units_to_usd_str(units)[1:]) * USD_UNITS) == units
