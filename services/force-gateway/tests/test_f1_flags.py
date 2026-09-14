"""Phase F1 — the gateway's enforcement posture against a FAKE sentinel:
flags and /health, the sentinel URL/timeout wiring, the timeout-vs-budget
relation, the self-manifest passthrough exemption (and its `llm.messages`
check), F3 token metering with an injected governor, and stage 2 against a
per-tool verdict table. The real spine is in tests/test_f1_enforce.py."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from field_core import llm as llm_mod

from force_gateway import api as api_mod
from force_gateway.api import (
    DEFAULT_SENTINEL_TIMEOUT,
    EGRESS_ACTION,
    SELF_AGENT_ID,
    SELF_AGENT_IDS,
    SentinelClient,
    SentinelUnavailable,
    create_app,
    mock_upstream,
    resolve_enforce,
    resolve_sentinel_timeout,
    resolve_sentinel_url,
    resolve_tool_check,
)

from test_gateway_delta import FakeGovernor, FakeLedger

SYNTHETIC_KEY = "SYNTHETIC-anthropic-key-not-real"
MSG = {"model": "m", "max_tokens": 16, "system": "caller system prompt",
       "messages": [{"role": "user", "content": "ping"}]}
HEADERS = {"x-field-agent-id": "rogue-agent", "x-field-token": "tok-rogue"}


class FakeSentinel:
    """Records every check; answers from `verdicts` (action -> verdict dict)
    or the default verdict; raises when `down`."""

    base_url = "http://fake-sentinel"

    def __init__(self, decision="ALLOW", clause_id=None, reasons=None,
                 context=None, verdicts=None, down=False):
        self.calls: list[tuple[str, str, str]] = []
        self.default = {"decision": decision, "clause_id": clause_id,
                        "reasons": reasons or [], "context": context or {}}
        self.verdicts = verdicts or {}
        self.down = down

    def check(self, agent_id, token_id, action):
        self.calls.append((agent_id, token_id, action))
        if self.down:
            raise SentinelUnavailable("fake sentinel down")
        verdict = self.verdicts.get(action, self.default)
        return {"agent_id": agent_id, "action": action, **verdict}


class Spy:
    def __init__(self, respond=mock_upstream):
        self.bodies = []
        self.respond = respond

    def __call__(self, body, headers):
        self.bodies.append(json.loads(json.dumps(body)))
        return self.respond(body, headers)


def gateway(sentinel=None, *, enforce=True, tool_check=False, upstream=None,
            governor=None, ledger=None, **kw):
    spy = upstream or Spy()
    ledger = ledger if ledger is not None else FakeLedger()
    app = create_app(upstream=spy, governor_client=governor, ledger_client=ledger,
                     sentinel_client=sentinel, enforce=enforce, tool_check=tool_check,
                     sample_every=0, latency_budget_ms=10_000.0, **kw)
    return TestClient(app), spy, ledger


# --- flags: exactly "1", never a near-miss; /health says what is on --------

@pytest.mark.parametrize("value,on", [
    ("1", True), ("true", False), ("yes", False), (" 1", False), ("0", False), ("", False)])
def test_enforce_and_tool_check_flags_are_exactly_1(monkeypatch, value, on):
    monkeypatch.setenv("FORCE_GATEWAY_ENFORCE", value)
    monkeypatch.setenv("FORCE_GATEWAY_TOOL_CHECK", value)
    assert resolve_enforce() is on and resolve_tool_check() is on
    h = TestClient(create_app(upstream=mock_upstream)).get("/health").json()
    assert (h["enforce"], h["tool_check"], h["tool_check_active"]) == (on, on, on)


def test_flags_default_off_is_the_observer(monkeypatch):
    assert resolve_enforce() is False and resolve_tool_check() is False
    client = TestClient(create_app(upstream=mock_upstream))
    h = client.get("/health").json()
    assert h["enforce"] is False and h["tool_check"] is False
    assert h["tool_check_active"] is False and h["sentinel_url"] is None
    assert client.post("/v1/messages", json=MSG).status_code == 200  # no headers needed


def test_health_keeps_every_existing_field_and_adds_the_f1_posture():
    h = TestClient(create_app(upstream=mock_upstream)).get("/health").json()
    for key in ("ok", "service", "version", "mock", "judge", "sample_every",
                "bypass_remaining", "telemetry_store", "build_sha"):
        assert key in h, key
    assert {"enforce", "tool_check", "tool_check_active", "sentinel_url",
            "sentinel_timeout_seconds"} <= set(h)
    assert h["sentinel_timeout_seconds"] == DEFAULT_SENTINEL_TIMEOUT == 30.0


def test_tool_check_without_enforce_is_inert_and_health_says_so():
    fake = FakeSentinel(decision="BLOCK", clause_id="D.scope")
    bad = {"type": "tool_use", "id": "t1", "name": "transfer funds", "input": {}}
    respond = lambda body, headers: (200, {"model": "x", "content": [bad],
                                            "stop_reason": "tool_use",
                                            "usage": {"input_tokens": 1, "output_tokens": 1}})
    client, spy, ledger = gateway(fake, enforce=False, tool_check=True, upstream=Spy(respond))
    h = client.get("/health").json()
    assert h["tool_check"] is True and h["tool_check_active"] is False and h["enforce"] is False
    body = client.post("/v1/messages", json=MSG).json()
    assert body["content"] == [bad] and body["stop_reason"] == "tool_use"
    assert fake.calls == [] and ledger.events == []


def test_enforce_0_never_calls_the_sentinel_even_with_the_headers():
    fake = FakeSentinel(decision="BLOCK", clause_id="E.kill_switch")
    client, spy, ledger = gateway(fake, enforce=False)
    assert client.post("/v1/messages", json=MSG).status_code == 200
    assert client.post("/v1/messages", json=MSG, headers=HEADERS).status_code == 200
    assert fake.calls == [] and len(spy.bodies) == 2
    assert [e["event_type"] for e in ledger.events] == []


# --- the sentinel URL and timeout wiring ------------------------------------

@pytest.mark.parametrize("value", [None, "", "   "])
def test_sentinel_url_unset_under_enforce_is_503_naming_it_never_a_process_exit(monkeypatch, value):
    monkeypatch.setenv("FORCE_GATEWAY_ENFORCE", "1")
    if value is None:
        monkeypatch.delenv("FIELD_SENTINEL_URL", raising=False)
    else:
        monkeypatch.setenv("FIELD_SENTINEL_URL", value)
    ledger = FakeLedger()
    spy = Spy()
    client = TestClient(create_app(upstream=spy, ledger_client=ledger))  # never raises
    h = client.get("/health").json()
    assert h["enforce"] is True and h["sentinel_url"] is None
    r = client.post("/v1/messages", json=MSG, headers=HEADERS)
    assert r.status_code == 503, r.text
    assert "FIELD_SENTINEL_URL" in r.json()["detail"]
    assert spy.bodies == []
    assert [(e["event_type"], e["payload"]) for e in ledger.events] == [("gateway.refused", {
        "agent_id": "rogue-agent", "action": EGRESS_ACTION, "clause_id": None, "status": 503})]
    # and the 401 still comes first: identity before the sentinel's absence
    assert client.post("/v1/messages", json=MSG).status_code == 401


def test_sentinel_url_and_timeout_from_the_environment(monkeypatch):
    monkeypatch.setenv("FORCE_GATEWAY_ENFORCE", "1")
    monkeypatch.setenv("FIELD_SENTINEL_URL", "http://sentinel:8004/")
    app = create_app(upstream=mock_upstream)
    assert resolve_sentinel_url() == "http://sentinel:8004"
    assert isinstance(app.state.sentinel, SentinelClient)
    assert app.state.sentinel.base_url == "http://sentinel:8004"
    assert app.state.sentinel.timeout == DEFAULT_SENTINEL_TIMEOUT
    h = TestClient(app).get("/health").json()
    assert h["sentinel_url"] == "http://sentinel:8004" and h["sentinel_timeout_seconds"] == 30.0
    monkeypatch.setenv("FORCE_GATEWAY_SENTINEL_TIMEOUT", "45")
    assert resolve_sentinel_timeout() == 45.0
    assert create_app(upstream=mock_upstream).state.sentinel.timeout == 45.0


@pytest.mark.parametrize("junk", ["", "abc", "0", "-3"])
def test_sentinel_timeout_junk_or_non_positive_is_the_default(monkeypatch, junk):
    monkeypatch.setenv("FORCE_GATEWAY_SENTINEL_TIMEOUT", junk)
    assert resolve_sentinel_timeout() == DEFAULT_SENTINEL_TIMEOUT


def test_enforce_0_builds_no_sentinel_client_but_reports_the_url(monkeypatch):
    monkeypatch.setenv("FIELD_SENTINEL_URL", "http://sentinel:8004")
    app = create_app(upstream=mock_upstream)
    assert app.state.sentinel is None
    assert TestClient(app).get("/health").json()["sentinel_url"] == "http://sentinel:8004"


def test_sentinel_client_sends_the_check_body_and_perimeter_header(monkeypatch):
    import httpx

    monkeypatch.setenv("FIELD_SHARED_SECRET", "synthetic-shared-secret-for-tests")
    seen = {}

    class Resp:
        status_code = 200

        def json(self):
            return {"decision": "ALLOW", "clause_id": None, "reasons": [], "context": {}}

    class Client:
        def __init__(self, timeout=None, headers=None, **kw):
            seen["timeout"], seen["headers"] = timeout, dict(headers or {})

        def post(self, url, json=None, **kw):
            seen["url"], seen["json"] = url, json
            return Resp()

    monkeypatch.setattr(httpx, "Client", Client)
    sentinel = SentinelClient(base_url="http://sentinel:8004", timeout=12.5)
    assert sentinel.check("a", "t", "llm.messages")["decision"] == "ALLOW"
    assert seen["url"] == "http://sentinel:8004/check"
    assert seen["json"] == {"agent_id": "a", "token_id": "t", "action": "llm.messages"}
    assert seen["timeout"] == 12.5
    assert seen["headers"] == {"x-field-auth": "synthetic-shared-secret-for-tests"}


def _sentinel_structural_budget(monkeypatch) -> float:
    """The sentinel's own per-check budget: its four service clients' read
    timeouts (registry, delegation, governor, ledger) + the ledger health
    probe — read from the sentinel's code, never from a literal here."""
    import httpx

    from conformance_sentinel import api as sentinel_api
    from conformance_sentinel.engine import DelegationIntrospectClient, SpendStatusClient
    from field_core.clients import LedgerClient, RegistryClient

    budget = 0.0
    for client in (RegistryClient(base_url="http://t"), LedgerClient(base_url="http://t"),
                   DelegationIntrospectClient(base_url="http://t"),
                   SpendStatusClient(base_url="http://t")):
        budget += float(client._client.timeout.read)
    probed = {}
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None, **kw: probed.update(timeout=timeout) or
                        (_ for _ in ()).throw(ConnectionError("no network in tests")))
    sentinel_api._default_ledger_health("http://t")()
    return budget + float(probed["timeout"])


def test_default_sentinel_timeout_exceeds_the_sentinels_structural_budget(monkeypatch):
    budget = _sentinel_structural_budget(monkeypatch)
    assert budget == 22.0  # 4 x 5 s + the 2 s health probe, as the code stands
    assert DEFAULT_SENTINEL_TIMEOUT > budget


def test_the_documented_judge_on_timeout_covers_a_judged_check(monkeypatch):
    """A check that reaches the semantic judge adds the judge client's own
    timeout; the default does NOT cover that (documented in the README), the
    README's judge-on setting (60) does. Read from the judge's code."""
    import httpx

    from conformance_sentinel.judge import AnthropicJudgeClient

    structural = _sentinel_structural_budget(monkeypatch)  # real httpx clients, first
    seen = {}
    monkeypatch.setattr(httpx, "Client", lambda base_url="", timeout=None, headers=None, **kw:
                        seen.update(timeout=timeout) or object())
    monkeypatch.setenv("ANTHROPIC_API_KEY", SYNTHETIC_KEY)
    AnthropicJudgeClient()
    judged = structural + float(seen["timeout"])
    assert DEFAULT_SENTINEL_TIMEOUT < judged  # honest: the default is the structural budget
    monkeypatch.setenv("FORCE_GATEWAY_SENTINEL_TIMEOUT", "60")
    assert resolve_sentinel_timeout() > judged


# --- passthrough under enforce=1: the three self ids only -------------------

@pytest.mark.parametrize("self_id", sorted(SELF_AGENT_IDS))
def test_self_id_passthrough_is_checked_as_llm_messages_and_keeps_its_exemption(monkeypatch, self_id):
    """Headers exactly as field_core.llm builds them for a self-agent."""
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009")
    monkeypatch.setenv("FIELD_SELF_AGENT_ID", self_id)
    monkeypatch.setenv("FIELD_SELF_TOKEN_ID", "tok-self")
    fake = FakeSentinel()
    client, spy, ledger = gateway(fake)
    r = client.post("/v1/messages", json=MSG, headers=llm_mod.anthropic_headers(SYNTHETIC_KEY))
    assert r.status_code == 200, r.text
    assert fake.calls == [(self_id, "tok-self", EGRESS_ACTION)]
    assert spy.bodies == [MSG]  # forwarded untouched: no FORCE block
    t = client.get("/telemetry").json()
    assert t["coverage"]["passthrough"] == 1 and t["total_requests"] == 0
    assert [(e["event_type"], e["payload"]["agent_id"]) for e in ledger.events] == [
        ("gateway.passthrough", self_id)]


def test_self_id_passthrough_without_the_token_is_401(monkeypatch):
    monkeypatch.setenv("FORCE_GATEWAY_URL", "http://forcegw:8009")
    monkeypatch.setenv("FIELD_SELF_AGENT_ID", "conformance-sentinel")  # token unset
    fake = FakeSentinel()
    client, spy, _ = gateway(fake)
    r = client.post("/v1/messages", json=MSG, headers=llm_mod.anthropic_headers(SYNTHETIC_KEY))
    assert r.status_code == 401 and fake.calls == [] and spy.bodies == []


def test_self_id_passthrough_is_refused_when_the_sentinel_blocks(monkeypatch):
    fake = FakeSentinel(decision="BLOCK", clause_id="E.kill_switch", reasons=["killed"])
    client, spy, ledger = gateway(fake)
    r = client.post("/v1/messages", json=MSG, headers={
        "x-force-passthrough": "judge", "x-field-agent-id": SELF_AGENT_ID,
        "x-field-token": "tok-self"})
    assert r.status_code == 403 and r.json()["clause_id"] == "E.kill_switch"
    assert spy.bodies == [] and client.app.state.coverage["passthrough"] == 0


def test_non_self_passthrough_header_is_ignored_under_enforce():
    fake = FakeSentinel()
    client, spy, ledger = gateway(fake)
    r = client.post("/v1/messages", json=MSG,
                    headers={"x-force-passthrough": "judge", **HEADERS})
    assert r.status_code == 200
    assert fake.calls == [("rogue-agent", "tok-rogue", EGRESS_ACTION)]
    assert spy.bodies[0]["system"].startswith("# FORCE Runtime Protocol")  # injected
    t = client.get("/telemetry").json()
    assert t["by_preset"] == {"analysis": 1} and t["coverage"]["passthrough"] == 0
    assert "gateway.passthrough" not in [e["event_type"] for e in ledger.events]


def test_self_id_passthrough_still_needs_the_perimeter_secret(monkeypatch):
    monkeypatch.setenv("FIELD_SHARED_SECRET", "synthetic-shared-secret-for-tests")
    fake = FakeSentinel()
    client, spy, _ = gateway(fake)
    client.app.user_middleware.clear()  # simulate the route opened past authn
    r = client.post("/v1/messages", json=MSG, headers={
        "x-force-passthrough": "judge", "x-field-agent-id": SELF_AGENT_ID,
        "x-field-token": "tok-self"})  # no x-field-auth
    assert r.status_code == 200
    assert spy.bodies[0]["system"].startswith("# FORCE Runtime Protocol")  # not exempt
    assert client.app.state.coverage["passthrough"] == 0


# --- the refusal contract against the fake ----------------------------------

def test_escalate_body_carries_escalation_true_and_the_sentence():
    fake = FakeSentinel(decision="ESCALATE", clause_id="E.irreversible",
                        reasons=["irreversible action requires human approval"])
    client, spy, ledger = gateway(fake)
    r = client.post("/v1/messages", json=MSG, headers=HEADERS)
    assert r.status_code == 403
    body = r.json()
    assert body["decision"] == "ESCALATE" and body["escalation"] is True
    assert body["clause_id"] == "E.irreversible"
    assert body["reasons"][0] == "irreversible action requires human approval"
    assert "cannot pause for a human" in body["reasons"][-1]
    assert spy.bodies == []
    assert [e["payload"] for e in ledger.events] == [{
        "agent_id": "rogue-agent", "action": EGRESS_ACTION,
        "clause_id": "E.irreversible", "status": 403}]


def test_block_body_has_no_escalation_key_and_carries_retry_after():
    fake = FakeSentinel(decision="BLOCK", clause_id="E.rate_limit", reasons=["rate limit"],
                        context={"retry_after_seconds": 42, "token_id": "tok-rogue"})
    client, spy, _ = gateway(fake)
    body = client.post("/v1/messages", json=MSG, headers=HEADERS).json()
    assert body["decision"] == "BLOCK" and "escalation" not in body
    assert body["retry_after_seconds"] == 42
    assert set(body) == {"decision", "clause_id", "reasons", "agent_id", "action",
                         "retry_after_seconds"}


def test_a_refusal_ledger_failure_still_refuses():
    class BrokenLedger(FakeLedger):
        def append(self, *a, **kw):
            raise ConnectionError("ledger down (synthetic)")

    fake = FakeSentinel(decision="BLOCK", clause_id="D.revoked")
    client, spy, _ = gateway(fake, ledger=BrokenLedger())
    r = client.post("/v1/messages", json=MSG, headers=HEADERS)
    assert r.status_code == 403 and spy.bodies == []


# --- F3: token metering at the egress, with an injected governor ------------

def test_f3_a_forwarded_request_meters_the_response_tokens_for_the_header_agent():
    gov = FakeGovernor()
    client, spy, _ = gateway(FakeSentinel(), governor=gov)
    assert client.post("/v1/messages", json=MSG, headers=HEADERS).status_code == 200
    assert gov.posts == [("/usage", {
        "agent_id": "rogue-agent", "model": "force-gateway-mock (no upstream call made)",
        "input_tokens": 240, "output_tokens": 118, "note": "force-gateway LLM call"})]


def test_f3_a_refused_call_meters_nothing():
    gov = FakeGovernor()
    client, spy, _ = gateway(FakeSentinel(decision="BLOCK", clause_id="E.kill_switch"), governor=gov)
    assert client.post("/v1/messages", json=MSG, headers=HEADERS).status_code == 403
    down, spy2, _ = gateway(FakeSentinel(down=True), governor=gov)
    assert down.post("/v1/messages", json=MSG, headers=HEADERS).status_code == 503
    assert gov.posts == [] and spy.bodies == [] and spy2.bodies == []


# --- stage 2 against a per-tool verdict table --------------------------------

def _tools_upstream(*blocks, stop_reason="tool_use"):
    def respond(body, headers):
        return 200, {"model": "synthetic-tool-model", "content": list(blocks),
                     "stop_reason": stop_reason,
                     "usage": {"input_tokens": 7, "output_tokens": 3}}
    return Spy(respond)


def _tool(name):
    return {"type": "tool_use", "id": f"toolu_{name}", "name": name, "input": {"n": 1}}


def test_stage2_checks_every_tool_use_by_name_with_the_same_agent_and_token():
    fake = FakeSentinel(verdicts={
        "transfer funds": {"decision": "BLOCK", "clause_id": "D.scope", "reasons": ["out"]},
        "send email": {"decision": "ESCALATE", "clause_id": "E.escalation_trigger", "reasons": []},
    })
    text = {"type": "text", "text": "plan"}
    keep = _tool("read timesheets")
    client, spy, ledger = gateway(fake, tool_check=True,
                                  upstream=_tools_upstream(text, _tool("transfer funds"),
                                                           keep, _tool("send email")))
    r = client.post("/v1/messages", json=MSG, headers=HEADERS)
    assert r.status_code == 200
    assert fake.calls == [("rogue-agent", "tok-rogue", EGRESS_ACTION),
                          ("rogue-agent", "tok-rogue", "transfer funds"),
                          ("rogue-agent", "tok-rogue", "read timesheets"),
                          ("rogue-agent", "tok-rogue", "send email")]
    content = r.json()["content"]
    assert content[0] == text and content[2] == keep
    assert content[1]["type"] == "text" and "D.scope" in content[1]["text"]
    assert content[3]["type"] == "text" and "E.escalation_trigger" in content[3]["text"]
    assert r.json()["stop_reason"] == "tool_use"
    refused = [e["payload"] for e in ledger.events if e["event_type"] == "gateway.tool_refused"]
    assert refused == [{"agent_id": "rogue-agent", "tool": "transfer funds", "clause_id": "D.scope"},
                       {"agent_id": "rogue-agent", "tool": "send email",
                        "clause_id": "E.escalation_trigger"}]
    assert "gateway.refused" not in [e["event_type"] for e in ledger.events]


def test_stage2_in_scope_response_is_returned_unchanged():
    fake = FakeSentinel()
    upstream = _tools_upstream({"type": "text", "text": "ok"}, _tool("read timesheets"))
    client, _, ledger = gateway(fake, tool_check=True, upstream=upstream)
    r = client.post("/v1/messages", json=MSG, headers=HEADERS)
    assert r.json() == upstream.respond(MSG, {})[1]
    assert [e["event_type"] for e in ledger.events] == []


def test_stage2_all_stripped_flips_tool_use_to_end_turn_and_down_sentinel_strips():
    fake = FakeSentinel(verdicts={"transfer funds": {"decision": "BLOCK", "clause_id": "D.scope",
                                                     "reasons": []}})
    client, _, ledger = gateway(fake, tool_check=True,
                                upstream=_tools_upstream(_tool("transfer funds")))
    body = client.post("/v1/messages", json=MSG, headers=HEADERS).json()
    assert body["stop_reason"] == "end_turn" and body["content"][0]["type"] == "text"

    class DownAfterCall(FakeSentinel):
        def check(self, agent_id, token_id, action):
            if action != EGRESS_ACTION:
                self.calls.append((agent_id, token_id, action))
                raise SentinelUnavailable("down for the tool check")
            return super().check(agent_id, token_id, action)

    down = DownAfterCall()
    client, _, ledger = gateway(down, tool_check=True, upstream=_tools_upstream(_tool("read timesheets")))
    body = client.post("/v1/messages", json=MSG, headers=HEADERS).json()
    assert body["stop_reason"] == "end_turn"
    assert "sentinel unavailable" in body["content"][0]["text"]
    assert [e["payload"] for e in ledger.events if e["event_type"] == "gateway.tool_refused"] == [
        {"agent_id": "rogue-agent", "tool": "read timesheets", "clause_id": None}]


def test_stage2_applies_to_a_self_id_passthrough_too():
    fake = FakeSentinel(verdicts={"transfer funds": {"decision": "BLOCK", "clause_id": "D.scope",
                                                     "reasons": []}})
    client, spy, ledger = gateway(fake, tool_check=True, upstream=_tools_upstream(_tool("transfer funds")))
    r = client.post("/v1/messages", json=MSG, headers={
        "x-force-passthrough": "judge", "x-field-agent-id": SELF_AGENT_ID, "x-field-token": "tok-self"})
    assert r.status_code == 200 and spy.bodies == [MSG]
    assert r.json()["content"][0]["type"] == "text" and r.json()["stop_reason"] == "end_turn"
    assert [e["payload"]["tool"] for e in ledger.events if e["event_type"] == "gateway.tool_refused"] == [
        "transfer funds"]


# --- the wire contract is shared with field_core.llm -----------------------

def test_header_and_action_names_are_the_ones_field_core_llm_publishes():
    assert api_mod.AGENT_ID_HEADER == llm_mod.AGENT_ID_HEADER == "x-field-agent-id"
    assert api_mod.TOKEN_HEADER == llm_mod.TOKEN_HEADER == "x-field-token"
    assert EGRESS_ACTION == llm_mod.EGRESS_ACTION == "llm.messages"
    assert SELF_AGENT_IDS == {"conformance-sentinel", "force-gateway", "compliance-crosswalk"}
