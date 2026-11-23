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


def test_the_problem_text_echoes_exactly_the_first_40_characters_and_nothing_past_them(monkeypatch):
    # 40 distinct, position-numbered characters then a tail: any longer echo or any 8-character piece of the tail shows
    value = "z" + "".join(f"{n:03d}" for n in range(1, 60))
    monkeypatch.setenv(RETENTION_ENV, value)
    days, problem = estate_retention_days()
    assert days is None and repr(value[:40]) in problem
    assert value[:41] not in problem
    assert all(value[k:k + 8] not in problem for k in range(40, len(value) - 7))


def test_a_value_longer_than_the_digit_bound_is_refused_not_a_crash(monkeypatch):
    # int() raises ValueError past 4300 digits (CPython default), and the fullmatch above lets such a value through
    monkeypatch.setenv(RETENTION_ENV, "1" * 5000)
    days, problem = estate_retention_days()
    assert days is None and problem is not None and "is not an integer" in problem
    assert "1" * 41 not in problem


def test_the_digit_bound_is_nine_digits_and_zero_padding_counts(monkeypatch):
    monkeypatch.setenv(RETENTION_ENV, "999999999")
    assert estate_retention_days() == (999999999, None)
    monkeypatch.setenv(RETENTION_ENV, "000000030")
    assert estate_retention_days() == (30, None)
    for raw in ("1000000000", "0000000030", "-1000000000"):
        monkeypatch.setenv(RETENTION_ENV, raw)
        days, problem = estate_retention_days()
        assert days is None and "is not an integer" in problem, raw


def test_a_five_thousand_digit_value_does_not_500_get_retention_check(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from sealed_ledger.api import create_app
    from sealed_ledger.store import LedgerStore

    monkeypatch.setenv(RETENTION_ENV, "1" * 5000)
    path = tmp_path / "ledger" / "events.jsonl"
    path.parent.mkdir(parents=True)
    r = TestClient(create_app(store=LedgerStore(path), registry=None), raise_server_exceptions=False).get("/retention/check")
    assert r.status_code == 200, r.status_code
    assert "1" * 41 not in r.text


def test_below_one_includes_the_value_one(monkeypatch):
    monkeypatch.setenv(RETENTION_ENV, "1")
    assert estate_retention_days() == (1, None)
