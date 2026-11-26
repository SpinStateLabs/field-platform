"""Kill-switch ledger rows are keyed by a registry agent id.

/kill, /revive, /drill and GET /heartbeat answer 422 to a path id outside the registry's id rule (at most 128
characters), after the route guard and before the registry is asked; every ledger row carries the registry record's
own ``agent_id`` once the record is read, and the validated path id otherwise; the guard's ``operator.refused`` row
carries no agent id for an invalid one. A row the ledger refuses (4xx) is attempted once more in a fixed shape. A
valid id behaves as before.

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from field_core.clients import (AgentNotRegisteredError, AgentRowChangedError, LedgerUnreachableError, RegistryClient,
                                RegistryUnreachableError)
from kill_switch import api as kill_api
from kill_switch.api import create_app

KEY_DON = "tkv-pdon-key-0123456789abcdef"
#: spelled here, not imported, so that this file collects on a tree without the constant (its tests then fail, not error)
FALLBACK_REASON = "the ledger refused this row; fixed-shape record"
BODY = {"operator": "someone", "reason": "path-id"}
ROUTES = ["kill", "revive", "drill"]
ALL_ROUTES = ROUTES + ["heartbeat"]
VERSION = "2026-01-01T00:00:00+00:00"
#: percent-encoded as sent; the router decodes them once
BAD_IDS = ["live%3F", "live%3Fx%3D1", "live%23f", "live%20x", "%20live", "live%20", "live%09x", "live%0Ax", "Live",
           ".live", "-live", "%2E%2E", "%2E", "live%2525", "live%00", "live%1Fx", "live%7F", "live%E2%80%AE",
           "live%E2%80%8F", "live%E2%80%A8", "%EF%BB%BFlive", "a" * 129, "a" * 201, "a" * 5000, "a" * 300 + "%3F"]


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


def call(client, route, path_id, headers=None):
    if route == "heartbeat":
        return client.get(f"/heartbeat/{path_id}", headers=headers or {})
    return client.post(f"/{route}/{path_id}", json=BODY, headers=headers or {})


def ids(led):
    return [(t, a) for t, _, a in led.rows]


# --- an invalid id: 422, nothing read, nothing written ---------------------------------------------------------------

@pytest.mark.parametrize("route", ALL_ROUTES)
@pytest.mark.parametrize("bad", BAD_IDS)
def test_an_invalid_id_is_422_and_reaches_neither_the_registry_nor_the_ledger(stack, route, bad):
    client, reg, led = stack
    r = call(client, route, bad, don())
    assert r.status_code == 422, (r.status_code, r.text)
    assert r.json() == {"detail": "agent_id is not a valid agent id"}
    assert reg.reads == [] and reg.writes == [] and led.rows == []


@pytest.mark.parametrize("route", ALL_ROUTES)
@pytest.mark.parametrize("bad", ["live%2Fx", "a%2F..%2Flive"])
def test_an_encoded_slash_matches_no_route_and_reads_nothing(stack, route, bad):
    client, reg, led = stack
    r = call(client, route, bad, don())
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


# --- the length bound ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("route", ALL_ROUTES)
def test_an_id_of_the_bound_is_asked_for_as_it_is(stack, route):
    client, reg, led = stack
    long_id = "a" * 128
    assert call(client, route, long_id, don()).status_code == (200 if route == "heartbeat" else 404)
    assert reg.reads == [long_id] and reg.writes == []
    assert ids(led) == ([("kill.agent.failed", long_id)] if route == "kill" else [])


def test_a_stored_agent_with_an_id_of_the_bound_can_be_killed(stack):
    client, reg, led = stack
    long_id = "a" * 128
    reg.agents[long_id] = _row(long_id)
    assert client.post(f"/kill/{long_id}", json=BODY, headers=don()).status_code == 200
    assert reg.writes == [(long_id, "killed")]


def test_a_valid_poll_answers_as_before(stack):
    client, reg, led = stack
    body = client.get("/heartbeat/live").json()
    assert (body["agent_id"], body["status"], body["killed"]) == ("live", "active", False)
    assert reg.reads == ["live"] and led.rows == []


@pytest.mark.parametrize("record_id", [None, "", "Not Valid", "a" * 201, 7])
def test_a_record_naming_no_usable_id_leaves_the_rows_on_the_validated_path_id(stack, record_id):
    client, reg, led = stack
    reg.agents["live"]["agent_id"] = record_id
    assert client.post("/kill/live", json=BODY, headers=don()).status_code == 200
    assert ids(led) == [("kill.endpoint_skipped", "live"), ("kill.agent", "live")]


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


# --- a refused row (4xx) is attempted once more in a fixed shape -----------------------------------------------------

class PickyLedger(Ledger):
    """Refuses a row with ``status`` unless it is the fixed shape (or always, with ``refuse_all``)."""

    def __init__(self, status=422, refuse_all=False):
        super().__init__()
        self.status, self.refuse_all, self.attempts = status, refuse_all, 0

    def append(self, event_type, payload, agent_id=None):
        self.attempts += 1
        if self.refuse_all or payload.get("reason") != FALLBACK_REASON:
            raise LedgerUnreachableError(f"ledger append returned {self.status}", status_code=self.status)
        super().append(event_type, payload, agent_id)


def _kill_with(stack, ledger, path_id="live", headers=None):
    client, reg, _ = stack
    client.app.state.ledger = ledger
    r = client.post(f"/kill/{path_id}", json=BODY, headers=don() if headers is None else headers)
    health = client.get("/health").json()
    return r, (health["ledger_note_failures"], health["ledger_rows_lost"]), reg


def test_the_fallback_reason_is_the_one_this_file_expects():
    assert getattr(kill_api, "LEDGER_FALLBACK_REASON", None) == FALLBACK_REASON


@pytest.mark.parametrize("status", [400, 403, 413, 422])
def test_a_halt_whose_rows_are_refused_is_recorded_in_the_fixed_shape(stack, status):
    ledger = PickyLedger(status)
    r, counters, reg = _kill_with(stack, ledger)
    assert r.status_code == 200 and reg.writes == [("live", "killed")]
    assert ids(ledger) == [("kill.endpoint_skipped", "live"), ("kill.agent", "live")]
    for _, payload, _ in ledger.rows:
        shape = (payload["operator"], payload["reason"], payload["refused_status"])
        assert shape == ("don", FALLBACK_REASON, status)
        assert payload["operator_id_authenticated"] == "don"
        assert "operator_claimed" not in payload and "operator_body_claimed" not in payload
        assert BODY["reason"] not in json.dumps(payload) and BODY["operator"] not in json.dumps(payload)
    assert counters == (2, 0) and ledger.attempts == 4


@pytest.mark.parametrize("status", [500, 502, 503, None])
def test_an_outage_gets_no_second_attempt_and_the_kill_still_happens(stack, status):
    ledger = PickyLedger(status)
    r, counters, reg = _kill_with(stack, ledger)
    assert r.status_code == 200 and reg.writes == [("live", "killed")]
    assert ledger.rows == [] and ledger.attempts == 2 and counters == (2, 2)


def test_a_ledger_refusing_the_fixed_shape_too_is_counted_as_lost_and_does_not_block_the_kill(stack):
    ledger = PickyLedger(422, refuse_all=True)
    r, counters, reg = _kill_with(stack, ledger)
    assert r.status_code == 200 and reg.writes == [("live", "killed")]
    assert ledger.attempts == 4 and counters == (2, 2)


def test_a_healthy_ledger_counts_nothing(stack):
    client, _, _ = stack
    assert client.post("/kill/live", json=BODY, headers=don()).status_code == 200
    health = client.get("/health").json()
    assert (health["ledger_note_failures"], health["ledger_rows_lost"]) == (0, 0)


@pytest.mark.parametrize("mode", ["off", "log-only"])
def test_the_fixed_shape_names_no_operator_for_an_unauthenticated_caller(stack, monkeypatch, mode):
    monkeypatch.delenv(oa.ENV_REQUIRE)
    if mode == "off":
        monkeypatch.delenv(oa.ENV_REGISTRY)
    ledger = PickyLedger(422)
    claimed = {oa.HEADER_OPERATOR: "someone-claimed", oa.HEADER_KEY: "tkv-wrong-key-00000000000000"}
    r, _, _ = _kill_with(stack, ledger, headers=claimed)
    assert r.status_code == 200, r.text
    rows = [payload for event_type, payload, _ in ledger.rows if event_type.startswith("kill.")]
    assert len(rows) == 2
    for payload in rows:
        assert payload["operator"] == "(not recorded)" and payload.get("operator_id_authenticated") is None
        text = json.dumps(payload)
        assert "someone-claimed" not in text and BODY["operator"] not in text and "operator_claimed" not in payload


# --- the rows of the drill's other endings and of a failed signal name the record ------------------------------------

class ScriptedRegistry(Registry):
    """``write_script[n]`` replaces the n-th status write: an exception is raised; "no-version" answers without one."""

    def __init__(self, agents, write_script):
        super().__init__(agents)
        self.write_script = write_script

    def set_status(self, agent_id, status, **kw):
        step = self.write_script.get(len(self.writes) + 1)
        if isinstance(step, Exception):
            self.writes.append((agent_id, status))
            raise step
        answer = super().set_status(agent_id, status, **kw)
        if step == "no-version":
            answer.pop("updated_at", None)
        return answer


@pytest.mark.parametrize("script,ending,code", [
    ({1: "no-version"}, "kill.drill.restore_skipped", 409),
    ({2: AgentRowChangedError("path-text")}, "kill.drill.restore_skipped", 409),
    ({2: RegistryUnreachableError("registry returned 503")}, "kill.drill.restore_failed", 500),
], ids=["no-version-token", "row-changed-at-restore", "restore-write-failed"])
def test_every_drill_ending_row_names_the_record(stack, script, ending, code):
    client, _, led = stack
    client.app.state.registry = ScriptedRegistry({"path-text": _row("real-one")}, script)
    r = client.post("/drill/path-text", json=BODY, headers=don())
    assert r.status_code == code, (r.status_code, r.text)
    assert ids(led) == [("kill.drill.start", "real-one"), ("kill.endpoint_skipped", "real-one"),
                        (ending, "real-one"), ("kill.drill.complete", "real-one")]


def test_the_row_of_a_signal_that_raised_names_the_record(stack, monkeypatch):
    client, reg, led = stack
    reg.write_error = RegistryUnreachableError("registry returned 503")

    def boom(manifest_ref):
        raise RuntimeError("resolver down")

    monkeypatch.setattr(kill_api, "resolve_manifest_detail", boom)
    assert client.post("/kill/path-text", json=BODY, headers=don()).status_code == 502
    assert ids(led) == [("kill.endpoint_failed", "real-one"), ("kill.agent.failed", "real-one")]
    assert led.rows[0][1]["reason"] == "signal_error"


# --- a domain kill over a stored id outside the rule -----------------------------------------------------------------

class NoSignal:
    def __init__(self):
        self.calls = []

    def request(self, method, url, headers=None, timeout=None):
        self.calls.append(url)
        return httpx.Response(200)


def test_a_domain_kill_records_an_error_and_signals_nothing_for_a_stored_id_over_the_bound(stack):
    """the real registry client: the list is read, the over-long id is never put into a URL (``stack``: the operator
    file and ENFORCE)"""
    long_id, seen = "a" * 129, []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        return httpx.Response(200, json=[_row(long_id)])

    registry = RegistryClient(client=httpx.Client(transport=httpx.MockTransport(handler)), base_url="http://registry")
    led, endpoint = Ledger(), NoSignal()
    client = TestClient(create_app(registry=registry, ledger=led, endpoint_client=endpoint))
    r = client.post("/kill/domain/ops", json=BODY, headers=don())
    assert r.status_code == 502, r.text
    report = r.json()["detail"]
    assert report["killed"] == [] and report["already_killed"] == []
    [result] = report["results"]
    assert (result["agent_id"], result["outcome"]) == (long_id, "error") and result["error"].startswith("404:")
    assert seen == [("GET", "/agents")] and endpoint.calls == []
    assert ids(led) == [("kill.agent.failed", long_id), ("kill.domain", None)]
    assert led.rows[0][1]["failure_class"] == "not_registered"
    assert led.rows[1][1]["errored"] == [{"agent_id": long_id, "status_code": 404}]


def test_the_fixed_shape_row_carries_no_agent_id_outside_the_rule(stack):
    """a domain kill over a stored id outside the rule: the first row is keyed by it, the fixed shape is not"""
    long_id = "a" * 201

    class Refusing(Registry):
        def get_agent(self, agent_id):
            raise AgentNotRegisteredError(agent_id)

    client, _, _ = stack
    client.app.state.registry = Refusing({long_id: _row(long_id)})
    ledger = PickyLedger(422)
    client.app.state.ledger = ledger
    assert client.post("/kill/domain/ops", json=BODY, headers=don()).status_code == 502
    assert ids(ledger) == [("kill.agent.failed", None), ("kill.domain", None)]
