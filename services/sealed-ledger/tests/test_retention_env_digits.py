"""S12-24: FIELD_LEDGER_RETENTION_DAYS is ASCII digits (an optional minus keeps the pinned ">= 1" refusal), not whatever
int() accepts. int() also takes underscores ('3_65' is 365), a leading '+', and any Unicode decimal digit (Arabic-Indic,
fullwidth), so a typo or mis-encoded value silently became a retention floor."""
from __future__ import annotations

import pytest

from sealed_ledger.retention import RETENTION_ENV, estate_retention_days


@pytest.mark.parametrize("raw", ["3_65", "+30", "٣٠", "３０", "3_0", "+0", "1_0_0", "𝟑𝟎"], ids=repr)
def test_a_non_ascii_digit_underscore_or_plus_is_no_policy_with_a_reason(monkeypatch, raw):
    monkeypatch.setenv(RETENTION_ENV, raw)
    days, problem = estate_retention_days()
    assert days is None and problem is not None
    assert RETENTION_ENV in problem and "is not an integer" in problem


@pytest.mark.parametrize("raw,expected", [("30", 30), (" 30 ", 30), ("365", 365), ("0030", 30), ("\t7\n", 7)])
def test_plain_digits_still_parse(monkeypatch, raw, expected):
    monkeypatch.setenv(RETENTION_ENV, raw)
    assert estate_retention_days() == (expected, None)


@pytest.mark.parametrize("raw", ["0", "-5", "-1"])
def test_below_one_keeps_its_message_with_the_number(monkeypatch, raw):
    monkeypatch.setenv(RETENTION_ENV, raw)
    assert estate_retention_days() == (None, f"{RETENTION_ENV}={int(raw)} must be >= 1")


def test_the_problem_text_still_shows_at_most_40_characters_of_the_value(monkeypatch):
    monkeypatch.setenv(RETENTION_ENV, "3_" + "6" * 100)
    _, problem = estate_retention_days()
    assert "6" * 40 not in problem or len(problem) < 120
    assert "6" * 100 not in problem
