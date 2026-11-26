"""What the kill-switch writes and logs about the agent id when a request is refused.

The route guard refuses before the route has checked the path id, so its ``operator.refused`` row carries the id only
when it is inside the registry's id rule. A drill refused because the agent's row changed names the registry record. The
refusal of an id outside the rule is logged by one fixed line.

Each test names the mutants it is there to fail (the ids of the mutation run over this code).

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from field_core.clients import AgentRowChangedError
from kill_switch.api import create_app

from test_path_agent_id_validation import Ledger, Registry, _row

KEY_DON = "tkv-gdon-key-0123456789abcdef"
KEY_NOSCOPE = "tkv-gnos-key-0123456789abcdef"
BODY = {"operator": "someone", "reason": "guard-row"}
ROUTES = ["kill", "revive", "drill"]
#: outside the id rule, yet plain enough that a ledger label would show them as sent
OUTSIDE = ["Zz-Marker", ".zz-marker", "-zz-marker"]


@pytest.fixture()
def stack(tmp_path, monkeypatch):
    for name in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(name, raising=False)
    ops = tmp_path / "operators.json"
    ops.write_text(json.dumps([
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active", "scopes": ["*"]},
        {"operator_id": "noscope", "key_sha256": oa.key_sha256(KEY_NOSCOPE), "status": "active", "scopes": ["attest"]},
    ]), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    reg = Registry({"live": _row("live"),
                    # read by one id, the record names another: shows which of the two a row carries
                    "path-text": _row("real-one")})
    led = Ledger()
    return TestClient(create_app(registry=reg, ledger=led)), reg, led


def hdr(operator, key):
    return {oa.HEADER_OPERATOR: operator, oa.HEADER_KEY: key}


REFUSED_BY_THE_GUARD = {
    "no-credential": ({}, 401),
    "wrong-key": (hdr("don", "tkv-wrong-key-00000000000000"), 403),
    "unlisted-operator": (hdr("nobody", KEY_DON), 403),
    "missing-scope": (hdr("noscope", KEY_NOSCOPE), 403),
}


def refused_rows(led):
    return [(event_type, agent_id) for event_type, _, agent_id in led.rows]


# mutants R03 (the id mapper returns its input), G01 / G02 / G03 (the kill, revive or drill guard built without the
# mapper) and G04 (the shared guard ignores the mapper)
@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("who", REFUSED_BY_THE_GUARD)
@pytest.mark.parametrize("path_id", OUTSIDE)
def test_the_guard_refusal_row_has_no_agent_id_for_an_id_outside_the_rule(stack, route, who, path_id):
    client, reg, led = stack
    headers, status = REFUSED_BY_THE_GUARD[who]
    r = client.post(f"/{route}/{path_id}", json=BODY, headers=headers)
    assert r.status_code == status, r.text
    assert refused_rows(led) == [("operator.refused", None)]
    assert reg.reads == [] and reg.writes == []


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("who", REFUSED_BY_THE_GUARD)
def test_the_guard_refusal_row_keeps_a_valid_agent_id(stack, route, who):
    client, reg, led = stack
    headers, status = REFUSED_BY_THE_GUARD[who]
    r = client.post(f"/{route}/live", json=BODY, headers=headers)
    assert r.status_code == status, r.text
    assert refused_rows(led) == [("operator.refused", "live")]
    assert reg.reads == [] and reg.writes == []


# mutant D09 (this refused row keyed by the path id)
def test_a_drill_refused_for_a_changed_row_names_the_registry_record(stack):
    client, reg, led = stack
    reg.write_error = AgentRowChangedError("the row changed")
    r = client.post("/drill/path-text", json=BODY, headers=hdr("don", KEY_DON))
    assert r.status_code == 409, r.text
    assert refused_rows(led) == [("kill.drill.start", "real-one"), ("kill.drill.refused", "real-one")]
    assert led.rows[-1][1]["reason"] == "the agent's row changed while the drill started"


def _kill_switch_warnings(caplog):
    return [record.getMessage() for record in caplog.records if record.name == "kill_switch.api"]


# mutants Q03 (the line logged for the poll only) and Q04 (never logged)
@pytest.mark.parametrize("route", ROUTES)
def test_a_refused_id_is_logged_once_by_a_fixed_line_that_never_quotes_it(stack, caplog, route):
    client, _, _ = stack
    with caplog.at_level(logging.WARNING, logger="kill_switch.api"):
        r = client.post(f"/{route}/Zz-Marker", json=BODY, headers=hdr("don", KEY_DON))
    assert r.status_code == 422, r.text
    assert _kill_switch_warnings(caplog) == [
        f"kill-switch: {route} refused, the path id is outside the agent-id rule"]
    assert "zz-marker" not in caplog.text.lower().replace("%2f", "/")


# mutants Q02 (logged for every route, the poll included) and Q03
def test_a_refused_poll_is_not_logged(stack, caplog):
    client, _, _ = stack
    with caplog.at_level(logging.WARNING, logger="kill_switch.api"):
        r = client.get("/heartbeat/Zz-Marker", headers=hdr("don", KEY_DON))
    assert r.status_code == 422, r.text
    assert _kill_switch_warnings(caplog) == []
