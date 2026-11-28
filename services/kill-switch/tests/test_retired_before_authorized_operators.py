"""A retired agent answers 409 on /kill, /revive and /drill BEFORE the manifest's ``authorized_operators`` list is read.

The operator's key and the route's scope are checked first (the route guard), so an unauthenticated or out-of-scope
caller learns nothing about the target. Every identity that holds the scope, a list-bound one included, then gets the
retired 409; nothing is written to the registry or signalled for a retired agent. Non-retired targets and the domain
kill are unchanged.

Test key values are throwaway constants; nothing here reads a real key."""

from __future__ import annotations

import json

import pytest
import yaml
from fastapi.testclient import TestClient

from field_core import operator_auth as oa
from field_core.clients import AgentNotRegisteredError
from field_core.templates_api import template_data
from kill_switch.api import create_app

KEY_DON = "tkv-rdon-key-0123456789abcdef"
KEY_OTHER = "tkv-roth-key-0123456789abcdef"
KEY_NOSCOPE = "tkv-rnos-key-0123456789abcdef"
KEY_VERIFIER = "tkv-rver-key-0123456789abcdef"
VERIFIER = "svc-verifier-gb10"
BODY = {"operator": "someone", "reason": "retired-guard"}
ROUTES = ["kill", "revive", "drill"]
RETIRED = ["ret-nomanifest", "ret-listed", "ret-broken"]
SCOPED = [("don", KEY_DON), ("other", KEY_OTHER), (VERIFIER, KEY_VERIFIER)]


class Ledger:
    def __init__(self):
        self.rows = []

    def append(self, event_type, payload, agent_id=None):
        self.rows.append((event_type, dict(payload), agent_id))

    def of(self, event_type):
        return [(p, a) for t, p, a in self.rows if t == event_type]


class Registry:
    def __init__(self, agents):
        self.agents = {a["agent_id"]: dict(a) for a in agents}
        self.writes = []
        self.reads = []
        self.retired_on_reread = set()     # listed as stored, read by id as retired (a retire between the two reads)

    def get_agent(self, agent_id):
        self.reads.append(agent_id)
        if agent_id not in self.agents:
            raise AgentNotRegisteredError(agent_id)
        record = dict(self.agents[agent_id])
        if agent_id in self.retired_on_reread:
            record["status"] = "retired"
        return record

    def list_agents(self, domain=None, status=None):
        return [dict(a) for a in self.agents.values()
                if (status is None or a["status"] == status) and (domain is None or a.get("domain") == domain)]

    def set_status(self, agent_id, status, **kw):
        self.writes.append((agent_id, status))
        self.agents[agent_id]["status"] = status
        return dict(self.agents[agent_id])


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    for name in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY, oa.ENV_OPERATOR_KEY_FILE):
        monkeypatch.delenv(name, raising=False)


def _manifest(tmp_path, name, authorized):
    data = template_data("default")
    data["agent"]["name"] = name
    data["enforcement"]["kill_switch"]["authorized_operators"] = authorized
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return str(path)


@pytest.fixture()
def stack(tmp_path, monkeypatch):
    """ENFORCE: don is named by the listed manifests; other holds every route scope and is named by none; noscope holds
    an unrelated scope; the verifier is list-bound."""
    rows = [
        {"operator_id": "don", "key_sha256": oa.key_sha256(KEY_DON), "status": "active", "scopes": ["*"],
         "names": ["Don Hagell"]},
        {"operator_id": "other", "key_sha256": oa.key_sha256(KEY_OTHER), "status": "active",
         "scopes": ["kill", "revive", "drill"]},
        {"operator_id": "noscope", "key_sha256": oa.key_sha256(KEY_NOSCOPE), "status": "active", "scopes": ["attest"]},
        {"operator_id": VERIFIER, "key_sha256": oa.key_sha256(KEY_VERIFIER), "status": "active",
         "scopes": ["kill", "revive", "drill"], "names": ["FIELD canary (gate verification)"]},
    ]
    ops = tmp_path / "operators.json"
    ops.write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setenv(oa.ENV_REGISTRY, str(ops))
    monkeypatch.setenv(oa.ENV_REQUIRE, "1")
    listed = _manifest(tmp_path, "listed", ["Don Hagell"])
    reg = Registry([
        {"agent_id": "ret-nomanifest", "status": "retired", "domain": "canary", "manifest_ref": None},
        {"agent_id": "ret-listed", "status": "retired", "domain": "finance", "manifest_ref": listed},
        {"agent_id": "ret-broken", "status": "retired", "domain": "canary", "manifest_ref": str(tmp_path / "gone.yaml")},
        {"agent_id": "live-nomanifest", "status": "active", "domain": "ops", "manifest_ref": None},
        {"agent_id": "live-listed", "status": "active", "domain": "finance", "manifest_ref": listed},
    ])
    led = Ledger()
    return TestClient(create_app(registry=reg, ledger=led)), reg, led


def hdr(operator, key):
    return {oa.HEADER_OPERATOR: operator, oa.HEADER_KEY: key}


# --- no state leak: the key and the route scope are checked first ----------------------------------------------------

@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("headers,status", [
    ({}, 401),
    (hdr("don", "tkv-wrong-key-00000000000000"), 403),
    (hdr("nobody", KEY_DON), 403),
    (hdr("noscope", KEY_NOSCOPE), 403),
], ids=["no-credential", "wrong-key", "unknown-id", "no-route-scope"])
def test_an_unauthenticated_or_out_of_scope_caller_learns_nothing_about_a_retired_agent(stack, route, headers, status):
    client, reg, led = stack
    for target in RETIRED + ["live-listed"]:
        r = client.post(f"/{route}/{target}", json=BODY, headers=headers)
        assert r.status_code == status, (target, r.status_code, r.text)
        assert "retired" not in r.text, (target, r.text)
    assert reg.reads == [] and reg.writes == [] and [t for t, _, _ in led.rows if t.startswith("kill.")] == []


@pytest.mark.parametrize("route", ROUTES)
def test_the_refusal_body_is_the_same_for_a_retired_and_a_live_agent_without_the_scope(stack, route):
    client, _, _ = stack
    a = client.post(f"/{route}/ret-nomanifest", json=BODY, headers=hdr("noscope", KEY_NOSCOPE))
    b = client.post(f"/{route}/live-listed", json=BODY, headers=hdr("noscope", KEY_NOSCOPE))
    assert (a.status_code, a.json()) == (b.status_code, b.json())


# --- retired: 409 for every authenticated operator that holds the route's scope --------------------------------------

@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("target", RETIRED)
@pytest.mark.parametrize("operator,key", SCOPED, ids=["listed", "unlisted", "list-bound-verifier"])
def test_a_scoped_operator_gets_409_on_a_retired_agent_listed_or_not(stack, route, target, operator, key):
    client, reg, led = stack
    r = client.post(f"/{route}/{target}", json=BODY, headers=hdr(operator, key))
    assert r.status_code == 409, (r.status_code, r.text)
    assert "retired" in r.json()["detail"]
    assert reg.writes == [] and reg.agents[target]["status"] == "retired"
    assert led.of("operator.refused") == []
    assert client.get("/health").json()["refused_count"] == 0


@pytest.mark.parametrize("target", RETIRED)
@pytest.mark.parametrize("operator,key", SCOPED, ids=["listed", "unlisted", "list-bound-verifier"])
def test_the_ledger_row_of_a_refused_kill_of_a_retired_agent(stack, target, operator, key):
    client, _, led = stack
    assert client.post(f"/kill/{target}", json=BODY, headers=hdr(operator, key)).status_code == 409
    assert [t for t, _, _ in led.rows] == ["kill.agent.failed"]
    payload, agent_id = led.of("kill.agent.failed")[0]
    assert agent_id == target
    assert (payload["status_code"], payload["failure_class"], payload["operator"]) == (409, "retired", operator)


REFUSED_ROW = [("revive", "kill.revive.refused"), ("drill", "kill.drill.refused")]


@pytest.mark.parametrize("route,event_type", REFUSED_ROW, ids=["revive", "drill"])
@pytest.mark.parametrize("target", RETIRED)
@pytest.mark.parametrize("operator,key", SCOPED, ids=["listed", "unlisted", "list-bound-verifier"])
def test_the_ledger_row_of_a_refused_revive_or_drill_of_retired(stack, route, event_type, target, operator, key):
    """exactly one row per attempt, naming the authenticated operator; never the success type, never a failed kill"""
    client, _, led = stack
    assert client.post(f"/{route}/{target}", json=BODY, headers=hdr(operator, key)).status_code == 409
    assert [(t, a) for t, _, a in led.rows] == [(event_type, target)]
    payload = led.rows[0][1]
    assert (payload["operator"], payload["reason"]) == (operator, "agent is retired")


@pytest.mark.parametrize("route", ["revive", "drill"])
def test_a_ledger_that_cannot_be_written_does_not_change_the_409(stack, route):
    client, reg, led = stack

    def refuse(event_type, payload, agent_id=None):
        raise RuntimeError("ledger down")

    led.append = refuse
    assert client.post(f"/{route}/ret-nomanifest", json=BODY, headers=hdr("other", KEY_OTHER)).status_code == 409
    assert reg.writes == []


ROW_OF = [("kill", "kill.agent.failed")] + REFUSED_ROW
ROW_IDS = ["kill", "revive", "drill"]


@pytest.mark.parametrize("route,event_type", ROW_OF, ids=ROW_IDS)
def test_the_row_names_the_registry_record_not_the_path_text(stack, route, event_type):
    client, reg, led = stack
    reg.agents["path-text"] = dict(reg.agents["ret-nomanifest"])    # read by one id, the record says another
    assert client.post(f"/{route}/path-text", json=BODY, headers=hdr("other", KEY_OTHER)).status_code == 409
    assert [a for _, a in led.of(event_type)] == ["ret-nomanifest"]


@pytest.mark.parametrize("route,event_type", ROW_OF, ids=ROW_IDS)
def test_the_row_is_written_with_the_operator_layer_off(stack, monkeypatch, route, event_type):
    """OFF: ``operator`` is the body's free text and the payload carries no authenticated fields"""
    client, _, led = stack
    monkeypatch.delenv(oa.ENV_REQUIRE)
    monkeypatch.delenv(oa.ENV_REGISTRY)
    assert client.post(f"/{route}/ret-nomanifest", json=BODY).status_code == 409
    [(payload, agent_id)] = led.of(event_type)
    assert agent_id == "ret-nomanifest" and payload["operator"] == "someone"
    assert "operator_id_authenticated" not in payload


@pytest.mark.parametrize("route,event_type", ROW_OF, ids=ROW_IDS)
@pytest.mark.parametrize("headers,operator,authenticated", [
    ({}, "someone", None),
    (hdr("other", KEY_OTHER), "other", "other"),
], ids=["no-credential", "authenticated"])
def test_the_row_is_written_in_log_only(stack, monkeypatch, route, event_type, headers, operator, authenticated):
    """LOG-ONLY: the authenticated id when the credential is good, else the body's free text and a null identity"""
    client, _, led = stack
    monkeypatch.delenv(oa.ENV_REQUIRE)
    assert client.post(f"/{route}/ret-nomanifest", json=BODY, headers=headers).status_code == 409
    [(payload, agent_id)] = led.of(event_type)
    assert agent_id == "ret-nomanifest" and payload["operator"] == operator
    assert payload["operator_id_authenticated"] == authenticated


def test_the_domain_kill_of_an_agent_retired_between_the_list_and_the_re_read(stack):
    client, reg, led = stack
    reg.agents["raced"] = {"agent_id": "raced", "status": "active", "domain": "race",
                           "manifest_ref": reg.agents["live-listed"]["manifest_ref"]}
    reg.retired_on_reread.add("raced")
    r = client.post("/kill/domain/race", json=BODY, headers=hdr("other", KEY_OTHER))
    assert r.status_code == 502, r.text
    report = r.json()["detail"]
    assert report["skipped_retired"] == [] and report["killed"] == []
    [result] = report["results"]
    assert result["outcome"] == "error" and result["error"].startswith("409:")
    [(payload, agent_id)] = led.of("kill.agent.failed")
    assert agent_id == "raced" and payload["domain"] == "race" and payload["failure_class"] == "retired"
    [(domain_row, _)] = led.of("kill.domain")
    assert domain_row["errored"] == [{"agent_id": "raced", "status_code": 409}]
    assert reg.writes == [] and led.of("operator.refused") == []


# --- a non-retired agent is unchanged --------------------------------------------------------------------------------

@pytest.mark.parametrize("route", ROUTES)
@pytest.mark.parametrize("target,operator,key", [
    ("live-listed", "other", KEY_OTHER),
    ("live-listed", VERIFIER, KEY_VERIFIER),
    ("live-nomanifest", VERIFIER, KEY_VERIFIER),
], ids=["unlisted", "verifier-not-named", "verifier-no-manifest"])
def test_an_unlisted_operator_is_still_403_on_a_live_agent(stack, route, target, operator, key):
    client, reg, led = stack
    r = client.post(f"/{route}/{target}", json=BODY, headers=hdr(operator, key))
    assert r.status_code == 403, (r.status_code, r.text)
    assert reg.writes == [] and reg.agents[target]["status"] == "active"
    refused = led.of("operator.refused")
    assert len(refused) == 1 and refused[0][1] == target
    assert refused[0][0]["action"] == route and refused[0][0]["reason"] == "forbidden"
    assert [t for t, _, _ in led.rows if t.startswith("kill.")] == []


def test_the_domain_kill_is_unchanged_retired_skipped_and_the_live_agent_still_checked(stack):
    client, reg, led = stack
    r = client.post("/kill/domain/finance", json=BODY, headers=hdr("other", KEY_OTHER))
    assert r.status_code == 502, r.text                     # the live agent errored (403), as before
    report = r.json()["detail"]
    assert report["skipped_retired"] == ["ret-listed"]
    outcomes = {row["agent_id"]: row["outcome"] for row in report["results"]}
    assert outcomes == {"ret-listed": "skipped_retired", "live-listed": "error"}
    assert reg.writes == [] and [a for _, a in led.of("operator.refused")] == ["live-listed"]
    assert not [a for _, a in led.of("kill.agent.failed") if a == "ret-listed"]
