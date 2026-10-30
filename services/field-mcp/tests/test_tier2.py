"""Tier 2 controls. Mutants: W1 intent recorded after the call; W2 audit failure ignored; W3 rate limit removed; W4 operator
pair sent on reads; W5 PATCH body not narrowed; W6 out_dir offered; W7 reason not required; W8 request body in the audit
record; W9 read process lists Tier 2; W10 operator key in the audit record; W11 operator pair sent to the ledger append."""
import json

import pytest

from conftest import KEY, Stub, config_for
from field_mcp import audit as au, client as cl
from field_mcp.catalog import SERVICES
from field_mcp.config import Config, ServiceConfig
from field_mcp.tools import Dispatcher, build_specs

OP, OPKEY = "op-alice", "opkey-" + "Z9q2" * 4


@pytest.fixture
def two():
    target, ledger = Stub(), Stub()
    ledger.routes[("POST", "/events")] = (201, {"event_id": 1}, {})
    yield target, ledger
    target.close()
    ledger.close()


def write_disp(target, ledger, rate=10, operator=OP, operator_key=OPKEY, clock=None):
    svcs = {s: ServiceConfig(target.base, KEY) for s in SERVICES}
    svcs["sealed-ledger"] = ServiceConfig(ledger.base, KEY)
    cfg = Config(tier=2, services=svcs, operator=operator, operator_key=operator_key, write_rate_per_min=rate)
    ups = {s: cl.Upstream(s, c.base, c.key) for s, c in svcs.items()}
    limiter = au.RateLimiter(rate, clock) if clock else None
    return Dispatcher(cfg, ups, au.Audit(ups["sealed-ledger"], operator, "test-client"), limiter)


REGISTER = {"body": {"agent_id": "agent-1", "name": "A", "owner": "o"}, "reason": "onboarding agent-1"}


def test_schemas_offer_only_what_the_ruling_allows():
    specs = {s.name: s for s in build_specs(2)}
    rename = specs["agent_registry_rename_agent"].input_schema["properties"]["body"]
    assert list(rename["properties"]) == ["name"] and rename["required"] == ["name"] and rename["additionalProperties"] is False
    assert "out_dir" not in specs["sealed_ledger_export"].input_schema["properties"]
    for s in specs.values():
        if s.tier == 2:
            assert "reason" in s.input_schema["required"] and "WRITES (Tier 2)" in s.description


@pytest.mark.parametrize("body", [{"status": "killed"}, {"status": "retired"}, {"owner": "x"}, {"manifest_ref": "p"},
                                  {"domain": "d"}, {"name": None}, {}, {"name": "ok", "status": "killed"}])
def test_a_rename_that_could_change_status_or_authority_is_refused(two, body):
    d = write_disp(*two)
    r = d.call("agent_registry_rename_agent", {"agent_id": "a1", "body": body, "reason": "x"})
    assert r == {"status": "error", "error": "arguments refused"} and not two[0].requests and not two[1].requests


def test_export_cannot_choose_the_directory(two):
    r = write_disp(*two).call("sealed_ledger_export", {"out_dir": "/etc", "reason": "x"})
    assert r["status"] == "error" and not two[0].requests


def test_a_write_requires_a_reason(two):
    d = write_disp(*two)
    assert d.call("conformance_sentinel_check", {"body": {}})["status"] == "error"
    assert d.call("conformance_sentinel_check", {"body": {}, "reason": ""})["status"] == "error"
    assert not two[0].requests and not two[1].requests


def test_intent_is_on_the_ledger_before_the_call_and_the_outcome_after(two):
    target, ledger = two
    seq = []
    for st, name in ((target, "target"), (ledger, "ledger")):
        st.requests = type("L", (list,), {"append": lambda self, x, n=name: (seq.append((n, x["path"])), list.append(self, x))})()
    target.routes[("POST", "/agents")] = (201, {"agent_id": "agent-1"}, {})
    r = write_disp(target, ledger).call("agent_registry_create_agent", REGISTER)
    assert r["status"] == "ok" and r["audit"]["intent"] == "recorded" and r["audit"]["outcome"] == "recorded"
    assert seq == [("ledger", "/events"), ("target", "/agents"), ("ledger", "/events")]
    kinds = [json.loads(q["body"])["event_type"] for q in ledger.requests]
    assert kinds == ["mcp.write.intent", "mcp.write.outcome"]


def test_no_intent_record_means_no_write(two):
    target, ledger = two
    for status in (403, 500, 503):
        ledger.routes[("POST", "/events")] = (status, {}, {})
        r = write_disp(target, ledger).call("agent_registry_create_agent", REGISTER)
        assert r == {"status": "error", "error": "audit unavailable; no write made"}
    assert not target.requests


def test_ledger_unreachable_or_missing_means_no_write(two):
    target, ledger = two
    d = write_disp(target, ledger)
    d.audit.ledger = cl.Upstream("sealed-ledger", "http://127.0.0.1:1", KEY)
    assert d.call("agent_registry_create_agent", REGISTER)["error"] == "audit unavailable; no write made"
    d.audit.ledger = None
    assert d.call("agent_registry_create_agent", REGISTER)["error"] == "audit unavailable; no write made"
    d.audit = None
    assert d.call("agent_registry_create_agent", REGISTER)["error"] == "audit unavailable; no write made"
    assert not target.requests


def test_a_failed_outcome_record_is_reported_and_does_not_undo_the_write(two):
    target, ledger = two
    target.routes[("POST", "/agents")] = (201, {"ok": 1}, {})
    d = write_disp(target, ledger)
    real = d.audit._append
    n = {"i": 0}

    def flaky(*a, **k):
        n["i"] += 1
        if n["i"] == 2:
            raise cl.ToolError("x")
        return real(*a, **k)
    d.audit._append = flaky
    r = d.call("agent_registry_create_agent", REGISTER)
    assert r["status"] == "ok" and r["audit"]["outcome"] == "not_recorded"


def test_an_upstream_failure_is_an_error_with_an_outcome_record(two):
    target, ledger = two
    target.routes[("POST", "/agents")] = (409, {"detail": "dup"}, {})
    r = write_disp(target, ledger).call("agent_registry_create_agent", REGISTER)
    assert r == {"status": "error", "error": "agent-registry returned 409"}
    outcome = json.loads(ledger.requests[-1]["body"])
    assert outcome["event_type"] == "mcp.write.outcome" and outcome["payload"]["status"] == "agent-registry returned 409"


def test_rate_limit_is_per_session_and_refuses_before_any_request(two):
    target, ledger = two
    t = {"now": 0.0}
    d = write_disp(target, ledger, rate=2, clock=lambda: t["now"])
    target.routes[("POST", "/agents")] = (201, {}, {})
    assert d.call("agent_registry_create_agent", REGISTER)["status"] == "ok"
    assert d.call("agent_registry_create_agent", REGISTER)["status"] == "ok"
    before = (len(target.requests), len(ledger.requests))
    assert d.call("agent_registry_create_agent", REGISTER) == {"status": "error", "error": "write rate limit reached; no write made"}
    assert (len(target.requests), len(ledger.requests)) == before
    t["now"] = 61.0
    assert d.call("agent_registry_create_agent", REGISTER)["status"] == "ok"


def test_reads_do_not_use_the_write_rate_limit(two):
    d = write_disp(*two, rate=1)
    for _ in range(5):
        assert d.call("agent_registry_list_agents", {})["status"] == "ok"


def test_the_operator_pair_goes_to_the_written_service_only(two):
    target, ledger = two
    target.routes[("POST", "/agents")] = (201, {}, {})
    d = write_disp(target, ledger)
    d.call("agent_registry_list_agents", {})
    d.call("agent_registry_create_agent", REGISTER)
    reads = [r for r in target.requests if r["method"] == "GET"]
    writes = [r for r in target.requests if r["method"] == "POST"]
    assert reads and "x-field-operator" not in reads[0]["headers"] and "x-field-operator-key" not in reads[0]["headers"]
    assert writes[0]["headers"]["x-field-operator"] == OP and writes[0]["headers"]["x-field-operator-key"] == OPKEY
    for r in ledger.requests:
        assert "x-field-operator" not in r["headers"] and "x-field-operator-key" not in r["headers"]


def test_header_names_match_the_platform():
    from field_core import operator_auth
    from field_mcp import tools
    assert tools.OPERATOR_HEADER == operator_auth.HEADER_OPERATOR and tools.OPERATOR_KEY_HEADER == operator_auth.HEADER_KEY


def test_the_audit_record_has_identity_hash_and_reason_but_no_body_and_no_key(two):
    target, ledger = two
    target.routes[("POST", "/agents")] = (201, {}, {})
    write_disp(target, ledger).call("agent_registry_create_agent", REGISTER)
    raw = ledger.requests[0]["body"].decode()
    p = json.loads(raw)["payload"]
    assert p["operator"] == OP and p["client_name"] == "test-client" and p["reason"] == "onboarding agent-1"
    assert len(p["body_sha256"]) == 64 and p["tool"] == "agent_registry_create_agent" and p["session_id"]
    assert json.loads(ledger.requests[0]["body"])["agent_id"] == "agent-1"
    for forbidden in (OPKEY, KEY, '"owner"', "agent_registry_create_agent_body"):
        assert forbidden not in raw
    assert '"name": "A"' not in raw


def test_the_operator_key_is_redacted_from_results(two):
    target, ledger = two
    target.routes[("POST", "/agents")] = (201, {"echo": f"saw {OPKEY}"}, {})
    r = write_disp(target, ledger).call("agent_registry_create_agent", REGISTER)
    assert OPKEY not in json.dumps(r)


def test_the_read_process_lists_no_tier2_tool():
    assert not [s for s in build_specs(1) if s.tier == 2]
    cfg = Config(tier=1, services={})
    assert not [s for s in Dispatcher(cfg, {}).list_tools() if s.tier == 2]


def test_a_read_process_refuses_a_tier2_call_by_name(two):
    cfg = config_for(two[0], tier=1)
    d = Dispatcher(cfg, {s: cl.Upstream(s, two[0].base, KEY) for s in cfg.services})
    assert d.call("conformance_sentinel_check", {"body": {}, "reason": "x"}) == {"status": "error", "error": "unknown tool"}
    assert not two[0].requests


def test_tier2_surface_is_pinned():
    import hashlib
    blob = json.dumps([(s.name, s.description) for s in build_specs(2) if s.tier == 2], sort_keys=True).encode()
    assert hashlib.sha256(blob).hexdigest() == TIER2_SURFACE


TIER2_SURFACE = "2a74d06c9c24385c33e4925f5af257fe96d8153436bbe93305bb001bd000c204"
