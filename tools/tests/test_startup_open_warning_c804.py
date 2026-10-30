"""C-804 (Don ruling D-21): every served service logs ONE loud WARNING per
process when it starts open, naming the setting and never a value.

Each service is built through its REAL ``create_app()`` (the same table as
test_build_sha_health, plus claude-approver). The demo defaults are untouched:
the app still starts and answers; only the line is new. Remove the
``warn_open`` call from any one service and exactly that parameter fails.
"""

from __future__ import annotations

import importlib
import logging

import pytest
from fastapi.testclient import TestClient

from field_core import startup

#: module -> (service name, create_app kwargs, has an operator layer)
SERVICES: dict[str, tuple[str, dict, bool]] = {
    "agent_registry.api": ("agent-registry", {}, True),
    "attestation_reporter.api": ("attestation-reporter", {}, False),
    "claude_approver.api": ("claude-approver", {}, False),
    "compliance_crosswalk.api": ("compliance-crosswalk", {}, False),
    "conformance_sentinel.api": ("conformance-sentinel", {}, False),
    "delegation_authority.api": ("delegation-authority", {}, True),
    "federation_broker.api": ("federation-broker", {}, True),
    "force_gateway.api": ("force-gateway", {}, False),
    "incident_replay.api": ("incident-replay", {}, False),
    "kill_switch.api": ("kill-switch", {}, True),
    "lifecycle_manager.api": ("lifecycle-manager", {}, True),
    "ops_console.api": ("ops-console", {}, True),
    "sealed_ledger.api": ("sealed-ledger", {}, True),
    "spend_governor.api": ("spend-governor", {}, True),
}

#: the settings each kind of service can leave open (names only)
PERIMETER = "FIELD_SHARED_SECRET"
OPERATOR = "FIELD_OPERATOR_REQUIRE"
SIGNING = ("FIELD_LEDGER_REQUIRE_SIGNING", "FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE")
ENFORCE = "FORCE_GATEWAY_ENFORCE"

# Made-up values: none is a real key or secret.
CANARIES = ["Kd8TvQ2wLcanaryONE", "Rm4XsZ9pBcanaryTWO", "Hy7NfC3eGcanaryTHREE"]


def _slices(value: str) -> list[str]:
    return [value[i:i + 4] for i in range(0, len(value) - 3)]


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch):
    startup._reset_for_tests()
    monkeypatch.setenv("FIELD_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("FIELD_MANIFEST_DIR", str(tmp_path / "data" / "manifests"))
    monkeypatch.setenv("FIELD_LIFECYCLE_EVERY", "0")
    for var in ("FIELD_SHARED_SECRET", "FIELD_SENTINEL_JUDGE", "FORCE_HYGIENE_JUDGE",
                "FIELD_DOA_ROSTER", "FIELD_LIFECYCLE_ROSTER", "FIELD_OPERATOR_REQUIRE",
                "FIELD_OPERATOR_REGISTRY", "FIELD_LEDGER_REQUIRE_SIGNING",
                "FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE", "FORCE_GATEWAY_ENFORCE"):
        monkeypatch.delenv(var, raising=False)
    yield
    startup._reset_for_tests()


def _build(module: str):
    _, kwargs, _ = SERVICES[module]
    return importlib.import_module(module).create_app(**kwargs)


def _lines(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "field_core.startup"]


def _expected(module: str) -> set[str]:
    _, _, operator_layer = SERVICES[module]
    want = {PERIMETER}
    if operator_layer:
        want.add(OPERATOR)
    if module == "sealed_ledger.api":
        want.update(SIGNING)
    if module == "force_gateway.api":
        want.add(ENFORCE)
    return want


def _named(message: str) -> set[str]:
    return {n for n in (PERIMETER, OPERATOR, ENFORCE, *SIGNING) if n in message}


def test_every_served_service_is_listed():
    """The thirteen compose/fly services plus claude-approver."""
    assert len(SERVICES) == 14


@pytest.mark.parametrize("module", sorted(SERVICES))
def test_an_open_service_logs_one_warning_naming_exactly_its_open_settings(module, caplog):
    caplog.set_level(logging.WARNING)
    app = _build(module)
    recs = _lines(caplog)
    assert len(recs) == 1 and recs[0].levelno == logging.WARNING
    assert SERVICES[module][0] in recs[0].getMessage()
    assert _named(recs[0].getMessage()) == _expected(module)
    # the demo default still starts and answers: a line, not a refusal
    assert TestClient(app).get("/health").status_code == 200


@pytest.mark.parametrize("module", sorted(SERVICES))
def test_the_line_appears_once_per_process(module, caplog):
    caplog.set_level(logging.WARNING)
    _build(module)
    _build(module)
    assert len(_lines(caplog)) == 1


@pytest.mark.parametrize("module", sorted(SERVICES))
def test_a_hardened_service_logs_nothing(module, caplog, monkeypatch):
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("FIELD_SHARED_SECRET", CANARIES[0])
    monkeypatch.setenv("FIELD_OPERATOR_REQUIRE", "1")
    monkeypatch.setenv("FORCE_GATEWAY_ENFORCE", "1")
    monkeypatch.setenv("FIELD_LEDGER_REQUIRE_SIGNING", "1")
    monkeypatch.setenv("FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE", "1")
    _build(module)
    assert _lines(caplog) == []


@pytest.mark.parametrize("module", sorted(SERVICES))
def test_no_value_reaches_the_log(module, caplog, monkeypatch):
    """Values sit in the settings the line names (flags set to something that is
    not an on-spelling) and in neighbours: none of it, nor any 4-character
    slice, may appear in any record's text, args or message template."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("FIELD_LEDGER_REQUIRE_SIGNING", CANARIES[0])
    monkeypatch.setenv("FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE", CANARIES[1])
    monkeypatch.setenv("FIELD_OPERATOR_KEY", CANARIES[2])
    monkeypatch.setenv("FIELD_LEDGER_SIGN_KEY", CANARIES[2])
    _build(module)
    recs = _lines(caplog)
    assert len(recs) == 1
    blob = " ".join(f"{r.getMessage()} {r.args!r} {r.msg!r}" for r in recs)
    for value in CANARIES:
        for piece in [value] + _slices(value):
            assert piece not in blob


def test_the_gateway_names_enforce_only_while_it_is_off(caplog, monkeypatch):
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("FORCE_GATEWAY_ENFORCE", "1")
    _build("force_gateway.api")
    assert ENFORCE not in _lines(caplog)[0].getMessage()


def test_a_refused_gateway_flag_is_not_echoed(caplog, monkeypatch):
    """A flag value the resolver refuses stops the app before any line (the
    posture rule of C-502) and the helper never reads it back or calls it off."""
    from force_gateway import api

    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("FORCE_GATEWAY_ENFORCE", CANARIES[0])
    with pytest.raises(api.InvalidPostureFlag) as err:
        _build("force_gateway.api")
    assert CANARIES[0] not in str(err.value)
    assert api._enforce_off_names() == []
    assert _lines(caplog) == []


def test_the_ledger_names_only_the_signing_settings_that_are_off(caplog, monkeypatch):
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("FIELD_LEDGER_REQUIRE_SIGNING", "1")
    _build("sealed_ledger.api")
    msg = _lines(caplog)[0].getMessage()
    assert SIGNING[0] not in msg and SIGNING[1] in msg
