"""S8-13 — FIELD_LIFECYCLE_EVERY through create_app: ASCII digits only. A non-decimal digit used to
crash startup (str.isdigit accepts '²', int() raises); any other non-blank bad value silently meant OFF.
Now it is OFF with a warning that names the variable and never the value. No floor: soak runs set a few
seconds. The upper bound (9 digits) keeps Event.wait from overflowing in the daemon thread."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from lifecycle_manager import api
from lifecycle_manager.api import MAX_EVERY_SECONDS, create_app

ENV = "FIELD_LIFECYCLE_EVERY"


class _Nothing:
    def __getattr__(self, name):
        raise AssertionError("no upstream call expected")


def _every(**kw) -> int:
    app = create_app(registry=_Nothing(), delegation=_Nothing(), ledger=_Nothing(), **kw)
    return TestClient(app).get("/health").json()["every"]


def test_the_python_facts_the_card_rests_on():
    assert "²".isdigit() and "٣".isdigit()
    with pytest.raises(ValueError):
        int("²")


@pytest.mark.parametrize("raw, want", [("5", 5), ("3600", 3600), ("0", 0), ("86400", 86400),
                                       (" 60 ", 60), ("3600 ", 3600), ("007", 7),
                                       ("999999999", 999_999_999)])
def test_plain_digits_are_the_interval(monkeypatch, caplog, raw, want):
    monkeypatch.setenv(ENV, raw)
    with caplog.at_level(logging.WARNING, logger="lifecycle_manager"):
        assert _every() == want
    assert caplog.text == ""


@pytest.mark.parametrize("raw", ["²", "٣", "１２", "1e3", "1.5", "-5", "+5", "3600s", "1_000", "abc",
                                 "1 2", "1000000000", "9" * 30])
def test_anything_else_is_off_with_a_warning_naming_the_variable_not_the_value(monkeypatch, caplog, raw):
    monkeypatch.setenv(ENV, raw)
    with caplog.at_level(logging.WARNING, logger="lifecycle_manager"):
        assert _every() == 0                      # no crash, scheduler OFF
    assert ENV in caplog.text
    assert raw.strip() not in caplog.text


@pytest.mark.parametrize("raw", ["", "   "])
def test_blank_is_off_silently(monkeypatch, caplog, raw):
    monkeypatch.setenv(ENV, raw)
    with caplog.at_level(logging.WARNING, logger="lifecycle_manager"):
        assert _every() == 0
    assert caplog.text == ""


def test_unset_is_off(monkeypatch):
    monkeypatch.delenv(ENV, raising=False)
    assert _every() == 0


def test_an_explicit_value_wins_over_the_environment(monkeypatch):
    monkeypatch.setenv(ENV, "²")
    assert _every(every=7) == 7


def test_an_explicit_value_past_the_bound_is_off_with_a_warning(caplog):
    with caplog.at_level(logging.WARNING, logger="lifecycle_manager"):
        assert _every(every=MAX_EVERY_SECONDS + 1) == 0
        assert _every(every=MAX_EVERY_SECONDS) == MAX_EVERY_SECONDS
    assert str(MAX_EVERY_SECONDS) in caplog.text and caplog.text.count("OFF") == 1


@pytest.mark.parametrize("every", [-5, 0, None])
def test_negative_and_zero_are_off(monkeypatch, every):
    monkeypatch.delenv(ENV, raising=False)
    assert _every(every=every) == 0


def test_the_bound_is_nine_digits():
    assert MAX_EVERY_SECONDS == 999_999_999 and api._EVERY_RE.pattern == "[0-9]{1,9}"
