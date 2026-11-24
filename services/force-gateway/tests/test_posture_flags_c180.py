"""C-180 (reviewer C-170 F-C170-1, D-24): unrecognised posture flags in force-gateway.

`FORCE_GATEWAY_ENFORCE`, `FORCE_GATEWAY_TOOL_CHECK` and `FORCE_GATEWAY_REQUIRE_TLS_UPSTREAM` were exact-match
`== "1"`: `true`, `yes`, `on`, `enforce`, ` 1` and `2` all left the gateway an observer, silently. A recognised
true (`1 true yes on`) arms, a recognised false (`0 false no off`) disarms (case-insensitive, whitespace ignored),
unset or blank is off, and any other non-empty value refuses to start. `FORCE_GATEWAY_MOCK` stays exact-match."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from field_core import posture_flag
from force_gateway import api
from force_gateway.api import (ENFORCE_ENV, REQUIRE_TLS_ENV, TOOL_CHECK_ENV, InvalidPostureFlag, create_app,
                               mock_upstream, resolve_enforce, resolve_require_tls_upstream, resolve_tool_check)

FLAGS = [(ENFORCE_ENV, resolve_enforce), (TOOL_CHECK_ENV, resolve_tool_check),
         (REQUIRE_TLS_ENV, resolve_require_tls_upstream)]
TRUE = ["1", "true", "yes", "on", "TRUE", "Yes", "ON", " 1", "1 ", "\ttrue\n", " On "]
FALSE = ["0", "false", "no", "off", "FALSE", "No", "OFF", " 0", "\toff\n"]
BLANK = ["", " ", "\t", "  \n "]
BAD = ["2", "enforce", "enforced", "enable", "enabled", "y", "n", "t", "f", "tru", "yess", "of", "onn", "-1",
       "01", "1.0", "true!", "yes please", "1,0", "'1'", '"true"', "on off", "none", "null", "disabled"]


@pytest.mark.parametrize("var,fn", FLAGS)
def test_unset_is_off(monkeypatch, var, fn):
    monkeypatch.delenv(var, raising=False)
    assert fn() is False


@pytest.mark.parametrize("var,fn", FLAGS)
@pytest.mark.parametrize("raw", BLANK)
def test_blank_is_off(monkeypatch, var, fn, raw):
    monkeypatch.setenv(var, raw)
    assert fn() is False


@pytest.mark.parametrize("var,fn", FLAGS)
@pytest.mark.parametrize("raw", TRUE)
def test_every_true_spelling_arms(monkeypatch, var, fn, raw):
    monkeypatch.setenv(var, raw)
    assert fn() is True


@pytest.mark.parametrize("var,fn", FLAGS)
@pytest.mark.parametrize("raw", FALSE)
def test_every_false_spelling_is_off(monkeypatch, var, fn, raw):
    monkeypatch.setenv(var, raw)
    assert fn() is False


@pytest.mark.parametrize("var,fn", FLAGS)
@pytest.mark.parametrize("raw", BAD)
def test_anything_else_is_refused(monkeypatch, var, fn, raw):
    monkeypatch.setenv(var, raw)
    with pytest.raises(InvalidPostureFlag):
        fn()


@pytest.mark.parametrize("var", [ENFORCE_ENV, TOOL_CHECK_ENV, REQUIRE_TLS_ENV])
@pytest.mark.parametrize("raw", ["enforce", "2", "enable"])
def test_the_service_refuses_to_start_on_an_unrecognised_value(monkeypatch, var, raw):
    """The point of the card: the app cannot be built, so it cannot run as an observer by accident."""
    monkeypatch.setenv(var, raw)
    with pytest.raises(InvalidPostureFlag):
        create_app(upstream=mock_upstream)


@pytest.mark.parametrize("raw", ["enforce", "2"])
def test_a_bad_require_tls_value_refuses_to_start_even_when_the_posture_is_injected(monkeypatch, raw):
    monkeypatch.setenv(REQUIRE_TLS_ENV, raw)
    with pytest.raises(InvalidPostureFlag):
        create_app(upstream=mock_upstream, enforce=False, tool_check=False)


@pytest.mark.parametrize("raw", TRUE)
def test_a_recognised_true_arms_the_served_posture(monkeypatch, raw):
    monkeypatch.setenv(ENFORCE_ENV, raw)
    monkeypatch.setenv(TOOL_CHECK_ENV, raw)
    h = TestClient(create_app(upstream=mock_upstream)).get("/health").json()
    assert (h["enforce"], h["tool_check"]) == (True, True)


def test_the_message_names_the_variable_and_the_accepted_values_but_not_the_value_and_is_bounded(monkeypatch):
    monkeypatch.setenv(ENFORCE_ENV, "enforce")
    with pytest.raises(InvalidPostureFlag) as exc:
        resolve_enforce()
    msg = str(exc.value)
    assert ENFORCE_ENV in msg and "true" in msg and "false" in msg
    assert "'enforce'" not in msg and "=enforce" not in msg
    monkeypatch.setenv(ENFORCE_ENV, "x" * 5000)
    with pytest.raises(InvalidPostureFlag) as exc:
        resolve_enforce()
    assert len(str(exc.value)) < 300
    assert issubclass(InvalidPostureFlag, ValueError)


@pytest.mark.parametrize("raw,mock", [("1", True), ("true", False), ("yes", False), (" 1", False), ("2", False)])
def test_the_mock_switch_stays_exact_match(monkeypatch, raw, mock):
    """FORCE_GATEWAY_MOCK is untouched: only "1" selects the mock; anything else is the real, governed upstream."""
    monkeypatch.setenv("FORCE_GATEWAY_MOCK", raw)
    assert (api.resolve_upstream() is mock_upstream) is mock


@pytest.mark.parametrize("raw", ["true", "yes", "on", "1"])
def test_require_tls_refuses_a_plain_http_public_upstream_for_every_true_spelling(monkeypatch, raw):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://upstream.example.test:9000")
    monkeypatch.setenv(REQUIRE_TLS_ENV, raw)
    with pytest.raises(HTTPException) as exc:
        api.real_upstream({"model": "m", "messages": []}, {})
    assert exc.value.status_code == 502 and REQUIRE_TLS_ENV in exc.value.detail


@pytest.mark.parametrize("raw", ["enforce", "2"])
def test_require_tls_fails_closed_if_the_value_became_bad_after_start(monkeypatch, raw):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://upstream.example.test:9000")
    monkeypatch.setenv(REQUIRE_TLS_ENV, raw)
    with pytest.raises(HTTPException) as exc:
        api.real_upstream({"model": "m", "messages": []}, {})
    assert exc.value.status_code == 502


def test_the_shared_parser_returns_none_only_for_the_unrecognised():
    assert posture_flag.parse(None) is False
    assert posture_flag.parse("on") is True and posture_flag.parse("off") is False
    assert posture_flag.parse("enable") is None


CANARY = "Zq7-canary-Kd93Lm-Xw41"     # made up; a stand-in for a secret put in a flag variable by mistake


def _slices(text: str, n: int = 8):
    return [text[i:i + n] for i in range(len(text) - n + 1)]


@pytest.mark.parametrize("var,fn", FLAGS)
def test_the_value_of_a_flag_variable_never_reaches_the_exception_or_a_log(monkeypatch, caplog, var, fn):
    """C-502: the refusal names the variable only; no 8-character slice of the value (case preserved or folded)
    appears in the exception text, its args, its repr, the traceback text or any log record."""
    monkeypatch.setenv(var, CANARY)
    with caplog.at_level("DEBUG"):
        with pytest.raises(InvalidPostureFlag) as exc:
            fn()
        with pytest.raises(InvalidPostureFlag):
            create_app(upstream=mock_upstream)
    import traceback
    surfaces = [str(exc.value), repr(exc.value), repr(exc.value.args), "".join(traceback.format_exception(exc.value)),
                caplog.text]
    for surface in surfaces:
        low = surface.lower()
        for piece in _slices(CANARY):
            assert piece not in surface and piece.lower() not in low, piece
    assert var in str(exc.value)                      # the refusal itself still says which variable


def test_the_refusal_is_unchanged_for_every_bad_value(monkeypatch):
    for raw in BAD:
        monkeypatch.setenv(ENFORCE_ENV, raw)
        with pytest.raises(InvalidPostureFlag):
            resolve_enforce()
