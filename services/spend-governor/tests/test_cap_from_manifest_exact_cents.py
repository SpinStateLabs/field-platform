"""S9-9: a valid two-decimal manifest limit is converted to cents exactly, not refused as 'sub-cent'.

`from_manifest` did `cents = round(limit * 100)` and refused when `abs(cents - limit * 100) > 1e-9`. Float multiplication is not
exact: 131692.98 * 100 is 13169298.000000002 (a difference of about 1.9e-9), so a limit with exactly two decimals was refused as
having sub-cent precision (the README and SPEC promise only sub-cent limits are refused). Of 6,314 sampled cent amounts between
0.01 and 500,000.00 dollars, 446 were refused when the card was written. Now the conversion is
`Decimal(str(limit)) * 100`, refused only when that Decimal is not integral, and the cents come from the Decimal."""

import pytest

from field_core.manifest import FieldManifest
from field_core.templates_api import template_data
from spend_governor.core import SpendCapConfig, limit_to_cents


def manifest(limit):
    data = template_data("financial-agent")
    data["enforcement"]["spend_cap"]["limit"] = limit
    return FieldManifest.from_dict(data)


@pytest.mark.parametrize("limit, cents", [(131692.98, 13169298), (131772.17, 13177217), (131851.36, 13185136),
                                          (132722.45, 13272245), (0.29, 29), (1.15, 115), (100000.01, 10000001),
                                          (500.0, 50000), (0.01, 1), (1, 100)])
def test_a_two_decimal_limit_gives_exact_cents_through_from_manifest(limit, cents):
    assert SpendCapConfig.from_manifest(manifest(limit), "fin-agent").limit_cents == cents


@pytest.mark.parametrize("limit", [0.005, 12.345, 0.001, 1.001, 99.999, 131692.985])
def test_a_sub_cent_limit_is_still_refused(limit):
    with pytest.raises(ValueError, match="sub-cent"):
        SpendCapConfig.from_manifest(manifest(limit), "fin-agent")


def test_the_conversion_is_exact_for_every_cent_amount_from_one_to_two_million():
    for c in range(1, 2_000_001):
        assert limit_to_cents(c / 100) == c, c


def test_the_conversion_is_exact_where_the_float_check_used_to_fail_and_for_a_seeded_sample_up_to_500000_dollars():
    # the old check passes every amount below about $131,000: the failures start higher, so the range with the card's
    # four examples is covered in full and the rest by a seeded sample
    for c in range(13_100_000, 13_300_000):
        assert limit_to_cents(c / 100) == c, c
    import random
    rng = random.Random(20261107)
    for _ in range(300_000):
        c = rng.randint(1, 50_000_000)
        assert limit_to_cents(c / 100) == c, c


def test_limit_to_cents_refuses_a_non_integral_amount_and_returns_an_int():
    assert isinstance(limit_to_cents(1.25), int)
    for bad in (0.005, 12.345, 0.0001):
        with pytest.raises(ValueError, match="sub-cent"):
            limit_to_cents(bad)
