"""S8-22 — FIELD_LEDGER_REQUIRE_SIGNING / FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE keep their pinned parse
(1/true/yes/on arm; anything else is off), but a non-blank value outside {1,true,yes,on,0,false,no,off}
is made VISIBLE: one startup WARNING naming the variable (never the value) and a boolean on /health.
Whether a typo should instead refuse to start is Don's decision (not in this card)."""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient

from sealed_ledger.api import create_app, require_caller_signature_from_env, require_signing_from_env
from sealed_ledger.store import LedgerStore

VARS = [
    ("FIELD_LEDGER_REQUIRE_SIGNING", "require_signing_value_ignored", require_signing_from_env),
    ("FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE", "require_caller_signature_value_ignored",
     require_caller_signature_from_env),
]
IGNORED = ["enabled", "treu", "2", "ture", "y", "enable", "TRUEE", "1 1"]
RECOGNISED = ["1", "true", "yes", "on", "0", "false", "no", "off", "TRUE", " On ", "No", "OFF"]
BLANK = ["", "   "]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name, _, _ in VARS:
        monkeypatch.delenv(name, raising=False)


def _health(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger="sealed_ledger.api"):
        app = create_app(store=LedgerStore(tmp_path / "e.jsonl"))
    return TestClient(app).get("/health").json()


@pytest.mark.parametrize("name, flag, _", VARS)
@pytest.mark.parametrize("value", IGNORED)
def test_an_unrecognised_value_warns_once_and_shows_on_health(tmp_path, monkeypatch, caplog, name, flag, _, value):
    monkeypatch.setenv(name, value)
    h = _health(tmp_path, caplog)
    assert h[flag] is True
    warned = [r for r in caplog.records if name in r.getMessage()]
    assert len(warned) == 1 and warned[0].levelno == logging.WARNING
    assert value.strip() not in warned[0].getMessage() or len(value.strip()) <= 1   # never the value
    other = next(f for n, f, _ in VARS if n != name)
    assert h[other] is False                                     # only the variable that is wrong


@pytest.mark.parametrize("name, flag, _", VARS)
@pytest.mark.parametrize("value", RECOGNISED + BLANK)
def test_recognised_and_blank_values_do_not_warn(tmp_path, monkeypatch, caplog, name, flag, _, value):
    monkeypatch.setenv(name, value)
    h = _health(tmp_path, caplog)
    assert h[flag] is False
    assert not [r for r in caplog.records if name in r.getMessage()]


@pytest.mark.parametrize("name, flag, _", VARS)
def test_unset_does_not_warn(tmp_path, caplog, name, flag, _):
    assert _health(tmp_path, caplog)[flag] is False
    assert caplog.records == []


@pytest.mark.parametrize("name, flag, parse", VARS)
def test_the_pinned_parse_is_unchanged(monkeypatch, name, flag, parse):
    for value, want in [("1", True), ("true", True), ("YES", True), (" on ", True), ("0", False),
                        ("false", False), ("", False), ("enabled", False), ("2", False), ("treu", False)]:
        monkeypatch.setenv(name, value)
        assert parse() is want, (value, want)


def test_the_warning_carries_the_length_not_the_value(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("FIELD_LEDGER_REQUIRE_SIGNING", "SECRETLOOKINGVALUE")
    _health(tmp_path, caplog)
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "SECRETLOOKINGVALUE" not in text and "FIELD_LEDGER_REQUIRE_SIGNING" in text
