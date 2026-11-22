"""S2-11: interval_from_env never raises. `str.isdigit()` is True for '²' and '①', which `int()` rejects, and a digit
string past the interpreter's int-conversion limit raises too; both used to escape and, through from_env, stop
create_app at start."""

import pytest

from sealed_ledger import operator_observer as oo


@pytest.mark.parametrize("raw", ["²", "³", "①", "1²", "9" * 5000, "-5", "0", "5.0", "1e3", " ", "", None],
                         ids=["sup2", "sup3", "circled1", "1sup2", "5000-digits", "neg", "zero", "float", "exp", "blank", "empty", "none"])
def test_a_value_that_is_not_a_positive_ascii_integer_arms_nothing_and_never_raises(raw):
    assert oo.interval_from_env(raw) is None


@pytest.mark.parametrize("raw, expected", [(" 120 ", 120), ("1", oo.MIN_EVERY_S), ("120", 120)])
def test_a_positive_ascii_integer_is_the_interval_floored_at_the_minimum(raw, expected):
    assert oo.interval_from_env(raw) == expected


def test_from_env_with_a_superscript_value_is_not_armed_instead_of_raising():
    assert oo.from_env({oo.EVERY_ENV: "²"}, lambda *a: None, lambda: {}) == (None, None)


# reviewer-3 F-R596-1: digits that int() ACCEPTS but are not ASCII must not arm the observer ("takes only ASCII digits")
@pytest.mark.parametrize("raw", ["\u0661\u0662", "\uff11\uff12", "\u0967\u0968", "1\u0662", "\u0661"],
                         ids=["arabic-indic-12", "fullwidth-12", "devanagari-12", "mixed", "arabic-indic-1"])
def test_non_ascii_digits_that_int_accepts_arm_nothing(raw):
    assert int(raw) > 0        # the premise: int() itself would take these
    assert oo.interval_from_env(raw) is None
    assert oo.from_env({oo.EVERY_ENV: raw}, lambda *a: None, lambda: {}) == (None, None)
