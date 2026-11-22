"""C-804 (Don D-21): the startup open-mode line. Names a setting, never a value;
one line per service per process; never raises; the demo defaults still start."""

from __future__ import annotations

import logging

import pytest

from field_core import authn, operator_auth, startup

# Made-up values: none of these is a real key, secret or address.
CANARY = "zq9Wv4Kx7TcanaryPAYLOAD"
SLICES = [CANARY[i:i + 4] for i in range(0, len(CANARY) - 3)]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    startup._reset_for_tests()
    for var in (authn.ENV_VAR, operator_auth.ENV_REQUIRE, operator_auth.ENV_REGISTRY):
        monkeypatch.delenv(var, raising=False)
    yield
    startup._reset_for_tests()


def _lines(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "field_core.startup"]


def _text(rec: logging.LogRecord) -> str:
    return rec.getMessage() + " " + repr(rec.args) + " " + repr(rec.msg)


def test_an_open_service_logs_one_warning_naming_the_perimeter_setting(caplog):
    caplog.set_level(logging.WARNING)
    assert startup.warn_open("demo-svc") is True
    recs = _lines(caplog)
    assert len(recs) == 1 and recs[0].levelno == logging.WARNING
    assert "demo-svc" in recs[0].getMessage()
    assert "FIELD_SHARED_SECRET" in recs[0].getMessage()


def test_the_line_appears_once_per_service_per_process(caplog):
    caplog.set_level(logging.WARNING)
    assert startup.warn_open("svc-a") is True
    assert startup.warn_open("svc-a") is False
    assert startup.warn_open("svc-b") is True
    assert len(_lines(caplog)) == 2


def test_a_hardened_service_is_silent(caplog, monkeypatch):
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv(authn.ENV_VAR, CANARY)
    monkeypatch.setenv(operator_auth.ENV_REQUIRE, "1")
    assert startup.warn_open("svc", operator_layer=True) is False
    assert _lines(caplog) == []


def test_the_operator_layer_is_named_only_for_a_service_that_has_one(caplog):
    caplog.set_level(logging.WARNING)
    startup.warn_open("no-operator-layer")
    startup.warn_open("with-operator-layer", operator_layer=True)
    first, second = _lines(caplog)
    assert "FIELD_OPERATOR_REQUIRE" not in first.getMessage()
    assert "FIELD_OPERATOR_REQUIRE" in second.getMessage()


def test_log_only_is_not_off(caplog, monkeypatch):
    """A registry configured (LOG-ONLY) is a layer that is on: not named as off."""
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv(operator_auth.ENV_REGISTRY, "/does/not/matter.json")
    startup.warn_open("svc", operator_layer=True)
    assert "FIELD_OPERATOR_REQUIRE" not in _lines(caplog)[0].getMessage()


def test_extra_names_are_listed(caplog):
    caplog.set_level(logging.WARNING)
    startup.warn_open("svc", extra=["FIELD_LEDGER_REQUIRE_SIGNING", "FORCE_GATEWAY_ENFORCE"])
    msg = _lines(caplog)[0].getMessage()
    assert "FIELD_LEDGER_REQUIRE_SIGNING" in msg and "FORCE_GATEWAY_ENFORCE" in msg


def test_a_value_passed_where_a_name_belongs_is_dropped(caplog):
    """A caller bug (a value, a path, a key) must not reach the line."""
    caplog.set_level(logging.WARNING)
    startup.warn_open("svc", extra=[CANARY, "/etc/x", "has space", "lower_case", 7, None, "OK_NAME"])
    text = _text(_lines(caplog)[0])
    assert "OK_NAME" in text
    for bad in [CANARY, "/etc/x", "has space", "lower_case"] + SLICES:
        assert bad not in text


def test_the_secret_value_is_never_in_the_line(caplog, monkeypatch):
    """With the secret SET the perimeter is not named, and no value is read back
    into the line whichever other setting leaves the process open."""
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv(authn.ENV_VAR, CANARY)
    monkeypatch.setenv(operator_auth.ENV_REGISTRY, "")
    startup.warn_open("svc", operator_layer=True, extra=["FIELD_LEDGER_REQUIRE_SIGNING"])
    for rec in _lines(caplog):
        assert "FIELD_SHARED_SECRET" not in rec.getMessage()
        for piece in [CANARY] + SLICES:
            assert piece not in _text(rec)


def test_it_never_raises(monkeypatch, caplog):
    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(startup, "open_settings", boom)
    assert startup.warn_open("svc") is False


def test_the_name_guard_bounds_are_exact(caplog):
    """C-43 F-C43-1: a name of exactly 64 characters is listed, 65 is dropped,
    and trailing junk (a space, an equals sign, a newline) is dropped, not
    listed by its prefix. Pins both sides of the shape: the whole-string match
    and the 64-character bound."""
    caplog.set_level(logging.WARNING)
    ok64 = "A" + "B" * 63
    too_long = "A" + "B" * 64
    startup.warn_open("svc", extra=[
        ok64, too_long, "ZZTOP key=abc", "ZZTOP=abc", "NAME\n", "NAME ", " NAME",
        "A", "1BAD", "_BAD"])
    msg = _lines(caplog)[0].getMessage()
    assert ok64 in msg
    assert too_long not in msg and ("B" * 64) not in msg.replace(ok64, "")
    for dropped in ("ZZTOP", "key=abc", "NAME\n", "NAME ", "1BAD", "_BAD"):
        assert dropped not in msg
    assert startup.open_settings(extra=["A"]).count("A") == 1   # one letter is a name
    assert startup.open_settings(extra=[ok64]).count(ok64) == 1
    assert startup.open_settings(extra=[too_long]).count(too_long) == 0
