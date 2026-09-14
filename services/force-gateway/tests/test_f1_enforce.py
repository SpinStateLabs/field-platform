"""Phase F1 — the gateway as the LLM-egress enforcement point, proven against
the REAL in-process spine: registry + ledger + delegation + governor +
kill-switch + sentinel wired with TestClients (the sentinel conftest's Stack
pattern, COPIED here — never imported, so the two test trees stay
independent). `FORCE_GATEWAY_ENFORCE=1` is passed as `enforce=True`; every
other test module runs enforce=0 and is untouched by this phase.

Each refusal branch below has the test that fails if the branch is deleted
(the security-guard rule): the reviewer's mutation check is to neuter one
guard in `force_gateway.api` and watch exactly its test go red.
"""

from __future__ import annotations

import json

import pytest
import yaml
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from conformance_sentinel.api import create_app as create_sentinel_app
from conformance_sentinel.engine import (
    DelegationIntrospectClient,
    ManifestResolver,
    SentinelEngine,
    SpendStatusClient,
)
from conformance_sentinel.mode import SentinelMode
from delegation_authority.api import create_app as create_delegation_app
from delegation_authority.store import TokenStore
from field_core.clients import LedgerClient, RegistryClient
from field_core.templates_api import template_data
from kill_switch.api import create_app as create_killswitch_app
from kill_switch.store import HeartbeatStore
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore
from spend_governor.api import create_app as create_governor_app
from spend_governor.core import GovernorStore

from force_gateway.api import (
    EGRESS_ACTION,
    SELF_AGENT_ID,
    SentinelClient,
    SentinelUnavailable,
    create_app,
    mock_upstream,
)

AGENT_ID = "egress-agent"
SCOPE = ["read timesheets", "draft invoices", "send invoice email", EGRESS_ACTION]
MSG = {"model": "m", "max_tokens": 16, "system": "caller system prompt",
       "messages": [{"role": "user", "content": "ping"}]}


@pytest.fixture(autouse=True)
def _no_operator_spine_env(monkeypatch):
    """A roster or manifest dir from an operator's shell must not gate the
    in-process spine (the gateway conftest isolates the gateway's own vars)."""
    for var in ("FIELD_DOA_ROSTER", "FIELD_MANIFEST_DIR", "FIELD_KILL_ENDPOINT_ALLOWLIST"):
        monkeypatch.delenv(var, raising=False)


def build_manifest(tmp_path):
    data = template_data("default")
    data["agent"]["name"] = AGENT_ID
    data["agent"]["description"] = "Reads timesheets, drafts invoices; calls the model via the gateway"
    data["identity"]["principal"] = "Controller, Spin State Labs"
    data["identity"]["org"] = "Spin State Labs"
    data["identity"]["jurisdiction"] = ["PIPEDA"]
    data["identity"]["model_provider"] = "Anthropic"
    data["enforcement"]["kill_switch"]["endpoint"] = f"http://127.0.0.1:8005/kill/{AGENT_ID}"
    data["enforcement"]["kill_switch"]["method"] = "HTTP POST"
    data["enforcement"]["escalation_triggers"] = ["send invoice"]
    data["enforcement"]["spend_cap"] = {
        "currency": "USD", "limit": 500, "period": "daily", "on_breach": "halt",
    }
    data["ledger"]["store"] = "sealed-ledger service (hash-chained JSONL)"
    data["delegation"]["granted_by"] = "Controller, Spin State Labs"
    data["delegation"]["scope"] = list(SCOPE)
    data["delegation"]["expiry"] = "2027-06-30"
    data["delegation"]["revocation"] = {
        "method": "HTTP POST",
        "endpoint": "http://127.0.0.1:8003/tokens/{id}/revoke",
    }
    path = tmp_path / f"{AGENT_ID}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


class Spy:
    """Upstream spy: records every forwarded body; answers with `respond`."""

    def __init__(self, respond=mock_upstream):
        self.bodies = []
        self.respond = respond

    def __call__(self, body, headers):
        self.bodies.append(json.loads(json.dumps(body)))
        return self.respond(body, headers)


def tool_response(*blocks, stop_reason="tool_use"):
    """An upstream answering with the given content blocks (Messages shape)."""
    def respond(body, headers):
        return 200, {"id": "msg_tools", "type": "message", "role": "assistant",
                     "model": "synthetic-tool-model", "content": list(blocks),
                     "stop_reason": stop_reason,
                     "usage": {"input_tokens": 7, "output_tokens": 3}}
    return respond


def tool_use(name, **inputs):
    return {"type": "tool_use", "id": f"toolu_{name.replace(' ', '_')}",
            "name": name, "input": inputs}


class Stack:
    """The real spine, in-process. `mode` is the sentinel's operating mode."""

    def __init__(self, tmp_path, mode=SentinelMode.ENFORCE):
        self.ledger_store = LedgerStore(tmp_path / "events.jsonl")
        self.registry = TestClient(
            create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
        self.ledger = TestClient(create_ledger_app(store=self.ledger_store))
        ledger_client = LedgerClient(client=self.ledger, base_url="http://t")
        registry_client = RegistryClient(client=self.registry, base_url="http://t")
        self.delegation = TestClient(create_delegation_app(
            store=TokenStore(tmp_path / "tokens.sqlite3"),
            ledger=ledger_client, registry=registry_client))
        self.governor = TestClient(create_governor_app(
            store=GovernorStore(tmp_path / "spend.sqlite3"), ledger=ledger_client))
        self.killswitch = TestClient(create_killswitch_app(
            registry=registry_client, ledger=ledger_client,
            heartbeats=HeartbeatStore(tmp_path / "heartbeats.sqlite3")))
        self.manifest_path = build_manifest(tmp_path)
        engine = SentinelEngine(
            registry=registry_client,
            delegation=DelegationIntrospectClient(client=self.delegation, base_url="http://t"),
            governor=SpendStatusClient(client=self.governor, base_url="http://t"),
            ledger=ledger_client,
            ledger_health=lambda: True,
            manifests=ManifestResolver(manifest_dir=tmp_path),
            mode=mode,
        )
        self.sentinel = TestClient(create_sentinel_app(engine=engine))
        r = self.registry.post("/agents", json={
            "agent_id": AGENT_ID, "name": "Egress agent",
            "owner": "Controller, Spin State Labs", "domain": "finance",
            "manifest_ref": str(self.manifest_path)})
        assert r.status_code == 201, r.text
        self.set_cap()
        self.ledger_client = ledger_client

    def mint_token(self, scope=None, ttl=3600) -> str:
        r = self.delegation.post("/tokens", json={
            "agent_id": AGENT_ID, "granted_by": "Controller, Spin State Labs",
            "scope": scope or list(SCOPE), "ttl_seconds": ttl})
        assert r.status_code == 201, r.text
        return r.json()["token_id"]

    def revoke(self, token_id: str) -> None:
        assert self.delegation.post(f"/tokens/{token_id}/revoke").status_code == 200

    def set_cap(self, limit_cents=50_000) -> None:
        r = self.governor.put(f"/caps/{AGENT_ID}", json={
            "agent_id": AGENT_ID, "limit_cents": limit_cents,
            "period": "daily", "escalate_at_pct": 80})
        assert r.status_code == 200, r.text

    def kill(self) -> dict:
        r = self.killswitch.post(f"/kill/{AGENT_ID}", json={
            "operator": "Don Hagell", "reason": "F1 egress test"})
        assert r.status_code == 200, r.text
        assert self.registry.get(f"/agents/{AGENT_ID}").json()["status"] == "killed"
        return r.json()

    def events(self, event_type: str) -> list[dict]:
        return self.ledger_client.events(event_type)

    def gateway(self, upstream=None, *, enforce=True, tool_check=False,
                sentinel_client=None, **kw):
        spy = upstream or Spy()
        app = create_app(
            upstream=spy, governor_client=self.governor,
            ledger_client=self.ledger_client,
            sentinel_client=sentinel_client or SentinelClient(
                client=self.sentinel, base_url="http://t"),
            enforce=enforce, tool_check=tool_check, sample_every=0,
            latency_budget_ms=10_000.0, **kw)
        return TestClient(app), spy


@pytest.fixture()
def stack(tmp_path):
    return Stack(tmp_path)


def headers(token_id: str, agent_id: str = AGENT_ID, **more) -> dict:
    return {"x-field-agent-id": agent_id, "x-field-token": token_id, **more}


def refusals(stack) -> list[dict]:
    return [e["payload"] for e in stack.events("gateway.refused")]


# --- identity: both headers, or 401 (never ledgered, never forwarded) -------

@pytest.mark.parametrize("sent", [
    {},
    {"x-field-agent-id": AGENT_ID},
    {"x-field-token": "tok-without-agent"},
])
def test_missing_headers_401_names_both_headers_and_never_reaches_upstream(stack, sent):
    client, spy = stack.gateway()
    r = client.post("/v1/messages", json=MSG, headers=sent)
    assert r.status_code == 401, r.text
    detail = r.json()["detail"]
    assert "x-field-agent-id" in detail and "x-field-token" in detail
    assert "FORCE_GATEWAY_ENFORCE" in detail
    assert spy.bodies == []
    assert refusals(stack) == []  # a 401 is not a sentinel refusal
    assert stack.events("conformance.block") == []  # the sentinel was never asked


# --- ALLOW: forwarded as today, and metered for the header's agent (F3) -----

def test_allowed_call_is_forwarded_injected_and_metered_for_the_header_agent(stack):
    token = stack.mint_token()
    client, spy = stack.gateway()
    r = client.post("/v1/messages", json=MSG, headers=headers(token))
    assert r.status_code == 200, r.text
    assert r.json()["model"].startswith("force-gateway-mock")
    assert spy.bodies[0]["system"].startswith("# FORCE Runtime Protocol")  # injected
    assert "caller system prompt" in spy.bodies[0]["system"]
    # the sentinel checked exactly the fixed egress action, with the token
    allows = stack.events("conformance.allow")
    assert [(e["agent_id"], e["payload"]["action"]) for e in allows] == [(AGENT_ID, EGRESS_ACTION)]
    # F3: the response's own usage landed in the governor for THIS agent
    usage = stack.events("usage.recorded")
    assert [(e["agent_id"], e["payload"]["input_tokens"], e["payload"]["output_tokens"])
            for e in usage] == [(AGENT_ID, 240, 118)]
    status = stack.governor.get(f"/usage/{AGENT_ID}").json()
    assert (status["total_input_tokens"], status["total_output_tokens"]) == (240, 118)
    assert client.get("/telemetry").json()["total_requests"] == 1  # instrumented as today
    assert refusals(stack) == []


# --- the refusal branches (each one: 403 + clause + gateway.refused) --------

def test_killed_agent_is_refused_403_e_kill_switch_with_no_upstream_call(stack):
    token = stack.mint_token()
    client, spy = stack.gateway()
    assert client.post("/v1/messages", json=MSG, headers=headers(token)).status_code == 200
    stack.kill()
    r = client.post("/v1/messages", json=MSG, headers=headers(token))
    assert r.status_code == 403, r.text
    body = r.json()
    assert body["decision"] == "BLOCK" and body["clause_id"] == "E.kill_switch"
    assert body["reasons"] and body["agent_id"] == AGENT_ID and body["action"] == EGRESS_ACTION
    assert "escalation" not in body
    assert len(spy.bodies) == 1  # the refused call never reached the upstream
    events = stack.events("gateway.refused")
    assert [e["agent_id"] for e in events] == [SELF_AGENT_ID]  # the gateway signs its own event
    assert [e["payload"] for e in events] == [{
        "agent_id": AGENT_ID, "action": EGRESS_ACTION,
        "clause_id": "E.kill_switch", "status": 403}]


def test_a_refused_call_meters_nothing(stack):
    token = stack.mint_token()
    stack.kill()
    client, spy = stack.gateway()
    assert client.post("/v1/messages", json=MSG, headers=headers(token)).status_code == 403
    assert spy.bodies == []
    assert stack.events("usage.recorded") == []
    status = stack.governor.get(f"/usage/{AGENT_ID}").json()
    assert (status["total_input_tokens"], status["total_output_tokens"]) == (0, 0)
    assert client.get("/telemetry").json()["total_requests"] == 0


def test_revoked_token_is_refused_403_d_revoked(stack):
    token = stack.mint_token()
    client, spy = stack.gateway()
    stack.revoke(token)
    r = client.post("/v1/messages", json=MSG, headers=headers(token))
    assert r.status_code == 403 and r.json()["clause_id"] == "D.revoked", r.text
    assert spy.bodies == []
    assert [p["clause_id"] for p in refusals(stack)] == ["D.revoked"]


def test_unregistered_agent_is_refused_403(stack):
    token = stack.mint_token()
    client, spy = stack.gateway()
    r = client.post("/v1/messages", json=MSG, headers=headers(token, agent_id="ghost-agent"))
    assert r.status_code == 403 and r.json()["clause_id"] == "R.unregistered", r.text
    assert spy.bodies == []
    assert [p["agent_id"] for p in refusals(stack)] == ["ghost-agent"]


def test_over_cap_is_refused_403_e_spend_cap(stack):
    token = stack.mint_token()
    stack.set_cap(limit_cents=100)
    r = stack.governor.post("/spend", json={"agent_id": AGENT_ID, "cents": 100})
    assert r.status_code == 201 and r.json()["state"] == "BLOCK", r.text
    client, spy = stack.gateway()
    r = client.post("/v1/messages", json=MSG, headers=headers(token))
    assert r.status_code == 403 and r.json()["clause_id"] == "E.spend_cap", r.text
    assert spy.bodies == []
    assert [p["clause_id"] for p in refusals(stack)] == ["E.spend_cap"]


def test_throttled_is_refused_403_e_rate_limit_with_retry_after_seconds(stack):
    token = stack.mint_token()
    r = stack.governor.put(f"/rate-limits/{AGENT_ID}", json={
        "agent_id": AGENT_ID,
        "rate_limits": [{"action": EGRESS_ACTION, "max": 1, "period": "hourly"}]})
    assert r.status_code == 200, r.text
    client, spy = stack.gateway()
    assert client.post("/v1/messages", json=MSG, headers=headers(token)).status_code == 200
    r = client.post("/v1/messages", json=MSG, headers=headers(token))
    assert r.status_code == 403, r.text
    body = r.json()
    assert body["clause_id"] == "E.rate_limit"
    assert isinstance(body["retry_after_seconds"], int) and body["retry_after_seconds"] > 0
    assert len(spy.bodies) == 1
    assert [p["clause_id"] for p in refusals(stack)] == ["E.rate_limit"]


def test_x_field_action_is_enforced_against_the_scope(stack):
    token = stack.mint_token()
    client, spy = stack.gateway()
    r = client.post("/v1/messages", json=MSG,
                    headers=headers(token, **{"x-field-action": "transfer funds"}))
    assert r.status_code == 403 and r.json()["clause_id"] == "D.scope", r.text
    assert r.json()["action"] == "transfer funds"
    assert spy.bodies == []
    r = client.post("/v1/messages", json=MSG,
                    headers=headers(token, **{"x-field-action": "draft invoices"}))
    assert r.status_code == 200, r.text
    assert [e["payload"]["action"] for e in stack.events("conformance.allow")] == ["draft invoices"]
    assert [p["action"] for p in refusals(stack)] == ["transfer funds"]


def test_blank_x_field_action_falls_back_to_the_egress_action(stack):
    token = stack.mint_token()
    client, _ = stack.gateway()
    r = client.post("/v1/messages", json=MSG, headers=headers(token, **{"x-field-action": "   "}))
    assert r.status_code == 200, r.text
    assert [e["payload"]["action"] for e in stack.events("conformance.allow")] == [EGRESS_ACTION]


def test_escalate_is_403_with_escalation_true_and_the_human_sentence(stack):
    token = stack.mint_token()
    client, spy = stack.gateway()
    # the manifest declares the trigger "send invoice"; the action is in scope
    r = client.post("/v1/messages", json=MSG,
                    headers=headers(token, **{"x-field-action": "send invoice email"}))
    assert r.status_code == 403, r.text
    body = r.json()
    assert body["decision"] == "ESCALATE" and body["escalation"] is True
    assert body["clause_id"] == "E.escalation_trigger"
    assert any("cannot pause for a human" in reason for reason in body["reasons"])
    assert spy.bodies == []
    assert [p["clause_id"] for p in refusals(stack)] == ["E.escalation_trigger"]


class DownClient:
    """An httpx-like client whose every request fails (the sentinel is down)."""

    def post(self, url, **kw):
        raise ConnectionError("sentinel down (synthetic)")


class StatusClient:
    def __init__(self, status_code, body=None):
        self.status_code = status_code
        self.body = body

    def post(self, url, **kw):
        class Resp:
            status_code = self.status_code

            def json(_):
                if isinstance(self.body, Exception):
                    raise self.body
                return self.body
        return Resp()


@pytest.mark.parametrize("client_,why", [
    (DownClient(), "unreachable"),
    (StatusClient(500, {"detail": "boom"}), "returned 500"),
    (StatusClient(200, ValueError("not json")), "non-JSON"),
    (StatusClient(200, {"ok": True}), "no verdict"),
])
def test_sentinel_down_or_not_a_verdict_is_503_and_no_upstream_call(stack, client_, why):
    token = stack.mint_token()
    client, spy = stack.gateway(sentinel_client=SentinelClient(client=client_, base_url="http://t"))
    r = client.post("/v1/messages", json=MSG, headers=headers(token))
    assert r.status_code == 503, r.text
    assert why in r.json()["detail"]
    assert spy.bodies == []
    assert refusals(stack) == [{"agent_id": AGENT_ID, "action": EGRESS_ACTION,
                                "clause_id": None, "status": 503}]


def test_every_refusal_is_ledgered_in_order(stack):
    token = stack.mint_token()
    client, spy = stack.gateway()
    stack.kill()
    assert client.post("/v1/messages", json=MSG, headers=headers(token)).status_code == 403
    down, _ = stack.gateway(sentinel_client=SentinelClient(client=DownClient(), base_url="http://t"))
    assert down.post("/v1/messages", json=MSG, headers=headers(token)).status_code == 503
    assert [(p["status"], p["clause_id"]) for p in refusals(stack)] == [
        (403, "E.kill_switch"), (503, None)]
    assert spy.bodies == []


# --- enforcement precedes the bypass window; log-only is forwarded ---------

def test_enforcement_runs_before_the_bypass_window(stack):
    token = stack.mint_token()
    stack.kill()
    client, spy = stack.gateway()
    client.app.state.bypass_remaining = 3
    r = client.post("/v1/messages", json=MSG, headers=headers(token))
    assert r.status_code == 403 and r.json()["clause_id"] == "E.kill_switch"
    assert client.app.state.bypass_remaining == 3  # the refusal consumed no window
    assert client.app.state.coverage["bypassed"] == 0 and spy.bodies == []


def test_an_allowed_call_in_a_bypass_window_is_still_forwarded_uninstrumented(stack):
    token = stack.mint_token()
    client, spy = stack.gateway()
    client.app.state.bypass_remaining = 1
    assert client.post("/v1/messages", json=MSG, headers=headers(token)).status_code == 200
    assert spy.bodies == [MSG]  # bypass: no injection (hygiene fails open, as today)
    assert client.app.state.coverage["bypassed"] == 1
    assert [e["payload"]["action"] for e in stack.events("conformance.allow")] == [EGRESS_ACTION]


def test_log_only_sentinel_forwards_and_surfaces_the_shadow_context(tmp_path):
    stack = Stack(tmp_path, mode=SentinelMode.LOG_ONLY)
    token = stack.mint_token()
    stack.kill()
    client, spy = stack.gateway()
    r = client.post("/v1/messages", json=MSG, headers=headers(token))
    assert r.status_code == 200, r.text  # log-only: never blocked
    assert len(spy.bodies) == 1
    assert refusals(stack) == []
    assert [e["payload"] for e in stack.events("gateway.shadowed")] == [{
        "agent_id": AGENT_ID, "action": EGRESS_ACTION,
        "would_be": {"decision": "BLOCK", "clause_id": "E.kill_switch"}}]
    shadows = stack.events("conformance.shadow_block")
    assert [e["payload"]["would_block"] for e in shadows] == ["E.kill_switch"]


# --- stage 2: model-initiated tool intent, checked at the egress -----------

def test_stage2_out_of_scope_tool_use_is_stripped_and_ledgered_in_scope_passes(stack):
    token = stack.mint_token()
    text = {"type": "text", "text": "I will move the money and read the sheet."}
    bad, good = tool_use("transfer funds", amount=5), tool_use("read timesheets", week="37")
    client, spy = stack.gateway(Spy(tool_response(text, bad, good)), tool_check=True)
    r = client.post("/v1/messages", json=MSG, headers=headers(token))
    assert r.status_code == 200, r.text
    content = r.json()["content"]
    assert content[0] == text
    assert content[1]["type"] == "text"
    assert "transfer funds" in content[1]["text"] and "D.scope" in content[1]["text"]
    assert content[2] == good and json.dumps(content[2], sort_keys=True) == json.dumps(good, sort_keys=True)
    assert r.json()["stop_reason"] == "tool_use"  # one tool survived: the loop continues
    refused = stack.events("gateway.tool_refused")
    assert [e["payload"] for e in refused] == [
        {"agent_id": AGENT_ID, "tool": "transfer funds", "clause_id": "D.scope"}]
    # the sentinel was asked for the call and then once per tool, by name
    checked = [e["payload"]["action"] for e in stack.events("conformance.allow")]
    blocked = [e["payload"]["action"] for e in stack.events("conformance.block")]
    assert checked == [EGRESS_ACTION, "read timesheets"] and blocked == ["transfer funds"]
    assert refusals(stack) == []  # the CALL was allowed; only the tool was refused
    # hygiene telemetry measured the model's answer, not the gateway's refusal text
    assert client.get("/telemetry").json()["total_requests"] == 1


def test_stage2_in_scope_tools_pass_byte_identical(stack):
    token = stack.mint_token()
    blocks = ({"type": "text", "text": "ok"}, tool_use("read timesheets"), tool_use("draft invoices"))
    client, _ = stack.gateway(Spy(tool_response(*blocks)), tool_check=True)
    r = client.post("/v1/messages", json=MSG, headers=headers(token))
    assert r.status_code == 200
    _, expected = tool_response(*blocks)(MSG, {})
    assert r.json() == expected
    assert stack.events("gateway.tool_refused") == []


def test_stage2_all_tools_stripped_flips_stop_reason_to_end_turn(stack):
    token = stack.mint_token()
    client, _ = stack.gateway(Spy(tool_response(tool_use("transfer funds"), tool_use("delete ledger"))),
                              tool_check=True)
    r = client.post("/v1/messages", json=MSG, headers=headers(token))
    assert r.status_code == 200
    body = r.json()
    assert body["stop_reason"] == "end_turn"
    assert [b["type"] for b in body["content"]] == ["text", "text"]
    assert [e["payload"]["tool"] for e in stack.events("gateway.tool_refused")] == [
        "transfer funds", "delete ledger"]


def test_stage2_keeps_stop_reason_when_the_model_did_not_stop_for_tools(stack):
    token = stack.mint_token()
    client, _ = stack.gateway(Spy(tool_response(tool_use("transfer funds"), stop_reason="max_tokens")),
                              tool_check=True)
    body = client.post("/v1/messages", json=MSG, headers=headers(token)).json()
    assert body["stop_reason"] == "max_tokens"


def test_stage2_without_tool_check_leaves_tool_use_untouched(stack):
    token = stack.mint_token()
    bad = tool_use("transfer funds")
    client, _ = stack.gateway(Spy(tool_response(bad)), tool_check=False)
    body = client.post("/v1/messages", json=MSG, headers=headers(token)).json()
    assert body["content"] == [bad] and body["stop_reason"] == "tool_use"
    assert stack.events("gateway.tool_refused") == []
    assert [e["payload"]["action"] for e in stack.events("conformance.block")] == []


class FlakyAfterCall:
    """The real sentinel for the call check; DOWN for every tool check."""

    def __init__(self, real: SentinelClient):
        self.real = real
        self.base_url = real.base_url

    def check(self, agent_id, token_id, action):
        if action != EGRESS_ACTION:
            raise SentinelUnavailable("sentinel down during the tool check (synthetic)")
        return self.real.check(agent_id, token_id, action)


def test_stage2_sentinel_down_during_a_tool_check_strips_fail_closed(stack):
    token = stack.mint_token()
    flaky = FlakyAfterCall(SentinelClient(client=stack.sentinel, base_url="http://t"))
    client, _ = stack.gateway(Spy(tool_response(tool_use("read timesheets"))),
                              tool_check=True, sentinel_client=flaky)
    r = client.post("/v1/messages", json=MSG, headers=headers(token))
    assert r.status_code == 200  # the CALL was allowed; the tool could not be checked
    body = r.json()
    assert body["content"][0]["type"] == "text" and "read timesheets" in body["content"][0]["text"]
    assert body["stop_reason"] == "end_turn"
    assert [e["payload"] for e in stack.events("gateway.tool_refused")] == [
        {"agent_id": AGENT_ID, "tool": "read timesheets", "clause_id": None}]


def test_stage2_applies_in_a_bypass_window_too(stack):
    """Bypass drops instrumentation (fail-open hygiene), never enforcement."""
    token = stack.mint_token()
    client, _ = stack.gateway(Spy(tool_response(tool_use("transfer funds"))), tool_check=True)
    client.app.state.bypass_remaining = 1
    body = client.post("/v1/messages", json=MSG, headers=headers(token)).json()
    assert body["content"][0]["type"] == "text" and body["stop_reason"] == "end_turn"
    assert [e["payload"]["tool"] for e in stack.events("gateway.tool_refused")] == ["transfer funds"]
