"""A caller cannot choose the agent id text of a kill-switch ledger row.

/kill, /revive and /drill answer 422 to a path id outside the registry's id rule, after the route guard and before the
registry is asked; every ledger row carries the registry record's own ``agent_id`` once the record is read, and the
validated path id otherwise; the guard's ``operator.refused`` row carries no agent id for an invalid one. There is no
length bound: a stored row with a long id must stay killable. A valid id behaves as before.

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from field_core.clients import AgentNotRegisteredError, RegistryUnreachableError
from kill_switch.api import create_app

KEY_DON = "tkv-pdon-key-0123456789abcdef"
BODY = {"operator": "someone", "reason": "path-id"}
ROUTES = ["kill", "revive", "drill"]
VERSION = "2026-01-01T00:00:00+00:00"
#: percent-encoded as sent; the router decodes them once
BAD_IDS = ["live%3F", "live%3Fx%3D1", "live%23f", "live%20x", "%20live", "live%20", "live%09x", "live%0Ax", "Live",
           ".live", "-live", "%2E%2E", "%2E", "live%252F", "a" * 300 + "%3F"]


class Ledger:
    def __init__(self):
        self.rows = []

    def append(self, event_type, payload, agent_id=None):
        self.rows.append((event_type, dict(payload), agent_id))


class Registry:
    def __init__(self, agents):
        self.agents = {key: dict(row) for key, row in agents.items()}
        self.reads = []
        self.writes = []
        self.write_error = None

    def get_agent(self, agent_id):
        self.reads.append(agent_id)
        if agent_id not in self.agents:
            raise AgentNotRegisteredError(agent_id)
        return dict(self.agents[agent_id])

    def list_agents(self, domain=None, status=None):
        return [dict(a) for a in self.agents.values()]

    def set_status(self, agent_id, status, **kw):
        self.writes.append((agent_id, status))
        if self.write_error is not None:
            raise self.write_error
        self.agents[agent_id]["status"] = status
        return dict(self.agents[agent_id])


def _row(agent_id, status="active"):
    return {"agent_id": agent_id, "status": status, "domain": "ops", "manifest_ref": None, "updated_at": VERSION}


@pytest.fixture()
def stack(tmp_path, monkeypatch):
    for name in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(name, raising=False)
    ops = tmp_path / "operators.json"
    ops.write_text(json.dumps([{"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active",
                                "scopes": ["*"]}]), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    reg = Registry({"live": _row("live"), "gone": _row("gone", "retired"),
                    # read by one id, the record names another: shows which of the two a row carries
                    "path-text": _row("real-one")})
    led = Ledger()
    return TestClient(create_app(registry=reg, ledger=led)), reg, led


def don():
    return {oa.HEADER_OPERATOR: "don", oa.HEADER_KEY: KEY_DON}


def ids(led):
    return [(t, a) for t, _, a in led.rows]


# --- an invalid id: 422, nothing read, nothing written ---------------------------------------------------------------

@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("bad", BAD_IDS)
def test_an_invalid_id_is_422_and_reaches_neither_the_registry_nor_the_ledger(stack, route, bad):
    client, reg, led = stack
    r = client.post(f"/{route}/{bad}", json=BODY, headers=don())
    assert r.status_code == 422, (r.status_code, r.text)
    assert r.json() == {"detail": "agent_id is not a valid agent id"}
    assert reg.reads == [] and reg.writes == [] and led.rows == []


@pytest.mark.parametrize("route", ROUTES)
def test_an_encoded_slash_matches_no_route_and_reads_nothing(stack, route):
    client, reg, led = stack
    r = client.post(f"/{route}/live%2Fx", json=BODY, headers=don())
    assert r.status_code == 404, (r.status_code, r.text)
    assert reg.reads == [] and reg.writes == [] and led.rows == []


@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("path_id,row_id", [("live%3F", None), ("live", "live")], ids=["invalid", "valid"])
def test_a_refused_caller_leaves_operator_refused_without_an_invalid_agent_id(stack, route, path_id, row_id):
    """the guard runs first (401); the recorded ``path`` still shows what was asked for"""
    client, reg, led = stack
    assert client.post(f"/{route}/{path_id}", json=BODY).status_code == 401
    assert ids(led) == [("operator.refused", row_id)]
    assert led.rows[0][1]["path"].startswith(f"/{route}/live")
    assert reg.reads == []


# --- no length bound -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("route", ROUTES)
def test_an_over_long_id_inside_the_rule_is_asked_for_as_it_is(stack, route):
    client, reg, led = stack
    long_id = "a" * 5000
    assert client.post(f"/{route}/{long_id}", json=BODY, headers=don()).status_code == 404
    assert reg.reads == [long_id] and reg.writes == []
    assert ids(led) == ([("kill.agent.failed", long_id)] if route == "kill" else [])


def test_a_stored_agent_with_a_long_id_can_still_be_killed(stack):
    client, reg, led = stack
    long_id = "a" * 300
    reg.agents[long_id] = _row(long_id)
    assert client.post(f"/kill/{long_id}", json=BODY, headers=don()).status_code == 200
    assert reg.writes == [(long_id, "killed")]


# --- the rows name the record ----------------------------------------------------------------------------------------

@pytest.mark.parametrize("agent_id,record_id", [("live", "live"), ("path-text", "real-one")],
                         ids=["valid-id-unchanged", "record-wins-over-path"])
def test_kill_rows(stack, agent_id, record_id):
    client, reg, led = stack
    r = client.post(f"/kill/{agent_id}", json=BODY, headers=don())
    assert r.status_code == 200, r.text
    assert r.json()["agent_id"] == agent_id
    assert ids(led) == [("kill.endpoint_skipped", record_id), ("kill.agent", record_id)]


@pytest.mark.parametrize("agent_id,record_id", [("live", "live"), ("path-text", "real-one")],
                         ids=["valid-id-unchanged", "record-wins-over-path"])
def test_revive_row(stack, agent_id, record_id):
    client, _, led = stack
    assert client.post(f"/revive/{agent_id}", json=BODY, headers=don()).status_code == 200
    assert ids(led) == [("kill.revive", record_id)]


@pytest.mark.parametrize("agent_id,record_id", [("live", "live"), ("path-text", "real-one")],
                         ids=["valid-id-unchanged", "record-wins-over-path"])
def test_drill_rows(stack, agent_id, record_id):
    client, _, led = stack
    r = client.post(f"/drill/{agent_id}", json=BODY, headers=don())
    assert r.status_code == 200, r.text
    assert ids(led) == [("kill.drill.start", record_id), ("kill.endpoint_skipped", record_id),
                        ("kill.drill.complete", record_id)]
    assert led.rows[-1][1]["agent_id"] == record_id


def test_the_failed_write_rows_name_the_record(stack):
    client, reg, led = stack
    reg.write_error = RegistryUnreachableError("registry returned 503")
    assert client.post("/kill/path-text", json=BODY, headers=don()).status_code == 502
    assert ids(led) == [("kill.endpoint_skipped", "real-one"), ("kill.agent.failed", "real-one")]


def test_the_retired_refusal_row_names_the_record(stack):
    client, reg, led = stack
    reg.agents["path-gone"] = _row("gone", "retired")
    assert client.post("/kill/path-gone", json=BODY, headers=don()).status_code == 409
    assert ids(led) == [("kill.agent.failed", "gone")]


def test_the_drill_refusal_for_a_missing_row_version_names_the_record(stack):
    client, reg, led = stack
    reg.agents["path-text"]["updated_at"] = None
    assert client.post("/drill/path-text", json=BODY, headers=don()).status_code == 409
    assert ids(led) == [("kill.drill.refused", "real-one")]


def test_an_unknown_valid_id_is_recorded_as_sent(stack):
    client, reg, led = stack
    assert client.post("/kill/ghost", json=BODY, headers=don()).status_code == 404
    assert reg.reads == ["ghost"] and ids(led) == [("kill.agent.failed", "ghost")]
