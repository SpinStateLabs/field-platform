"""C-1065: reviewer C-1057 conditions on PR 380. One section per finding; each test fails without its fix.

Mutants (scripts/mutants.py): HF1 the header-safety check on the operator pair and the service keys removed; SG1 the
caller signer not handed to the audit; ID1 the agent id of `check` / `crossing` unbounded; ID2 top-level string
arguments of Tier 2 tools unbounded; SU1 the encodability check before the intent removed; SU2 the outcome row for an
error after the intent removed; U5 a 5xx on a write reported as a plain status; RZ1 the Zl and Zp separators kept;
RZ2 the visually blank filler characters kept.
"""
import json

import pytest

from conftest import KEY, Stub
from field_mcp import audit as au, client as cl
from field_mcp.catalog import SERVICES
from field_mcp.config import Config, ConfigError, ServiceConfig, load
from field_mcp.server import build_dispatcher
from field_mcp.tools import Dispatcher, build_specs

OP, OPKEY = "op-alice", "opkey-" + "Z9q2" * 4
W_ENV = {"FFMCP_ENABLE_WRITES": "1", "FFMCP_SEALED_LEDGER_URL": "http://127.0.0.1:1",
         "FFMCP_OPERATOR": OP, "FFMCP_OPERATOR_KEY": OPKEY}


@pytest.fixture
def two():
    target, ledger = Stub(), Stub()
    ledger.routes[("POST", "/events")] = (201, {"event_id": 1}, {})
    yield target, ledger
    target.close()
    ledger.close()


def write_disp(target, ledger, **kw):
    svcs = {s: ServiceConfig(target.base, KEY) for s in SERVICES}
    svcs["sealed-ledger"] = ServiceConfig(ledger.base, KEY)
    cfg = Config(tier=2, services=svcs, operator=OP, operator_key=OPKEY, **kw)
    ups = {s: cl.Upstream(s, c.base, c.key) for s, c in svcs.items()}
    return Dispatcher(cfg, ups, au.Audit(ups["sealed-ledger"], OP, "test-client"))


REGISTER = {"body": {"agent_id": "agent-1", "name": "A", "owner": "o"}, "reason": "onboarding agent-1"}
CHECK = {"body": {"agent_id": "agent-1", "action": "draft invoices"}, "reason": "dry run of a verdict"}


# ---- F-C1057-380-1: a header-unsafe character in a credential is refused at startup, naming the variable ------------

UNSAFE = ["k\n", "k\r\n", "k\t", "k\x00", "k\x7f", "kéy", "k "]


@pytest.mark.parametrize("bad", UNSAFE)
@pytest.mark.parametrize("var", ["FFMCP_OPERATOR", "FFMCP_OPERATOR_KEY", "FFMCP_AGENT_REGISTRY_KEY", "FFMCP_SEALED_LEDGER_KEY"])
def test_a_header_unsafe_character_in_a_credential_stops_the_write_process(var, bad):
    env = {**W_ENV, "FFMCP_AGENT_REGISTRY_URL": "http://127.0.0.1:2", var: bad}
    with pytest.raises(ConfigError) as e:
        load(2, env)
    assert var in str(e.value) and "Zq7" not in str(e.value)


def test_a_header_safe_credential_with_an_inner_space_and_punctuation_still_loads():
    cfg = load(2, {**W_ENV, "FFMCP_OPERATOR": "op alice", "FFMCP_OPERATOR_KEY": "k-._~+/=:;,@!#$%&*()[]{}<>|^`'\\\"?"})
    assert cfg.operator == "op alice"


def test_the_read_process_is_not_changed_by_the_check():
    assert load(1, {"FFMCP_AGENT_REGISTRY_URL": "http://127.0.0.1:2", "FFMCP_AGENT_REGISTRY_KEY": "k\n"}).tier == 1


# ---- F-C1057-380-3: the only production line that hands the caller signer to the audit is pinned --------------------

def test_build_dispatcher_gives_the_audit_the_configured_caller_signer():
    signer = object()
    cfg = Config(tier=2, services={"sealed-ledger": ServiceConfig("http://127.0.0.1:1", KEY)}, operator=OP,
                 operator_key=OPKEY, caller=signer)
    disp = build_dispatcher(cfg)
    assert disp.audit is not None and disp.audit.signer is signer and disp.audit.operator == OP


def test_build_dispatcher_without_a_caller_leaves_the_rows_unsigned_and_the_read_process_has_no_audit():
    cfg = Config(tier=2, services={"sealed-ledger": ServiceConfig("http://127.0.0.1:1", KEY)}, operator=OP, operator_key=OPKEY)
    assert build_dispatcher(cfg).audit.signer is None
    assert build_dispatcher(Config(tier=1, services={}, caller=object())).audit is None


def test_a_loaded_caller_reaches_the_audit_through_load_and_build_dispatcher(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    pem = Ed25519PrivateKey.generate().private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    key_file = tmp_path / "caller.pem"
    key_file.write_bytes(pem)
    cfg = load(2, {**W_ENV, "FFMCP_CALLER_ID": "ffmcp-test", "FFMCP_CALLER_KEY_FILE": str(key_file)})
    assert cfg.caller is not None
    assert build_dispatcher(cfg).audit.signer is cfg.caller


# ---- F-C1057-380-4 (carried F-C869-5): model-chosen ids are bounded before they can reach the append-only ledger ------

def _body_prop(tool, name):
    return {s.name: s for s in build_specs(2)}[tool].input_schema["properties"]["body"]["properties"][name]


def _string_members(schema):
    return [m for m in (schema.get("anyOf") or [schema]) if m.get("type") == "string"]


@pytest.mark.parametrize("tool", ["conformance_sentinel_check", "federation_broker_crossing"])
def test_the_agent_id_of_check_and_crossing_is_pattern_and_length_bound(tool):
    members = _string_members(_body_prop(tool, "agent_id"))
    assert members and all(m["pattern"] == "^[a-z0-9][a-z0-9._-]*$" and m["maxLength"] == 200 for m in members)


def test_the_other_ids_of_the_two_tools_have_a_length_cap():
    for tool, name in (("conformance_sentinel_check", "token_id"), ("federation_broker_crossing", "counterparty_agent_id")):
        members = _string_members(_body_prop(tool, name))
        assert members and all(m["maxLength"] == 200 for m in members), (tool, name)


def test_every_top_level_string_argument_of_a_tier2_tool_is_length_bound():
    for s in build_specs(2):
        if s.tier < 2:
            continue
        for name, prop in s.input_schema["properties"].items():
            if name in ("body", "reason"):
                continue
            for m in _string_members(prop):
                assert 0 < m.get("maxLength", 0) <= 200, (s.name, name)


@pytest.mark.parametrize("bad", ["x" * 1_000_000, "A" * 5, "agent 1", "agent-1\n", "-agent", "agent/../x", "agent\x00", "a" * 201, "agént"])
@pytest.mark.parametrize("tool,payload", [
    ("conformance_sentinel_check", CHECK),
    ("federation_broker_crossing", {"body": {"counterparty_org": "o", "scope": "s", "data_class": "d", "direction": "outbound",
                                             "agent_id": "agent-1"}, "reason": "a crossing"}),
])
def test_an_unbounded_or_odd_agent_id_is_refused_before_anything_is_sent_or_recorded(two, tool, payload, bad):
    target, ledger = two
    args = json.loads(json.dumps(payload))
    args["body"]["agent_id"] = bad
    assert write_disp(target, ledger).call(tool, args) == {"status": "error", "error": "arguments refused"}
    assert not target.requests and not ledger.requests


@pytest.mark.parametrize("good", ["agent-1", "a", "a" * 200, "a.b_c-9"])
def test_a_well_formed_agent_id_is_recorded_on_the_intent_row(two, good):
    target, ledger = two
    target.routes[("POST", "/check")] = (200, {"decision": "BLOCK"}, {})
    args = json.loads(json.dumps(CHECK))
    args["body"]["agent_id"] = good
    assert write_disp(target, ledger).call("conformance_sentinel_check", args)["status"] == "ok"
    assert json.loads(ledger.requests[0]["body"])["agent_id"] == good


def test_export_query_strings_cannot_be_unbounded(two):
    target, ledger = two
    r = write_disp(target, ledger).call("sealed_ledger_export", {"agent_id": "x" * 1000, "reason": "export"})
    assert r["status"] == "error" and not target.requests and not ledger.requests


# ---- F-C1057-380-2: no dangling intent row: an unencodable value is refused before the intent, and any error after it
#      writes an outcome row -----------------------------------------------------------------------------------------

LONE = "x\ud800y"


@pytest.mark.parametrize("args", [
    {"body": {"agent_id": "agent-1", "name": LONE, "owner": "o"}, "reason": "onboarding"},
    {"body": {"agent_id": "agent-1", "name": "A", "owner": {"k": [LONE]}}, "reason": "onboarding"},
    {"body": {"agent_id": "agent-1", "name": "A", "owner": "o"}, "reason": LONE},
])
def test_a_value_that_cannot_be_encoded_is_refused_before_any_row_and_uses_no_rate_slot(two, args):
    target, ledger = two
    target.routes[("POST", "/agents")] = (201, {"agent_id": "agent-1"}, {})
    d = write_disp(target, ledger, write_rate_per_min=1)
    assert d.call("agent_registry_create_agent", args) == {"status": "error", "error": "arguments refused"}
    assert not target.requests and not ledger.requests
    assert d.call("agent_registry_create_agent", REGISTER)["status"] == "ok"        # the one slot was still free


def test_an_unencodable_query_value_is_refused_before_any_row(two):
    target, ledger = two
    r = write_disp(*two).call("sealed_ledger_export", {"since": LONE, "reason": "export"})
    assert r == {"status": "error", "error": "arguments refused"} and not target.requests and not ledger.requests


def test_an_unexpected_error_after_the_intent_writes_an_outcome_row_and_says_outcome_unknown(two, monkeypatch):
    target, ledger = two
    d = write_disp(target, ledger)

    def boom(*a, **k):
        raise RuntimeError("Zq7-secret-looking-text")
    monkeypatch.setattr(d.upstreams["agent-registry"], "request", boom)
    r = d.call("agent_registry_create_agent", REGISTER)
    assert r == {"status": "error", "error": "agent-registry outcome unknown; do not retry; check with a read tool"}
    kinds = [json.loads(q["body"])["event_type"] for q in ledger.requests]
    assert kinds == ["mcp.write.intent", "mcp.write.outcome"]
    outcome = json.loads(ledger.requests[-1]["body"])["payload"]
    assert outcome["status"] == "agent-registry outcome unknown; do not retry; check with a read tool"
    assert "Zq7" not in json.dumps(r) and "Zq7" not in ledger.requests[-1]["body"].decode()


# ---- F-C1057-380-5: a 5xx on a write is not a refusal: a gateway may have forwarded a request the service acted on ----

UNKNOWN = "agent-registry outcome unknown; do not retry; check with a read tool"


@pytest.mark.parametrize("status", [500, 501, 502, 503, 504, 599])
def test_a_5xx_on_a_write_is_outcome_unknown_in_the_result_and_on_the_ledger(two, status):
    target, ledger = two
    target.routes[("POST", "/agents")] = (status, {"detail": "Zq7-body-text"}, {})
    r = write_disp(target, ledger).call("agent_registry_create_agent", REGISTER)
    assert r == {"status": "error", "error": UNKNOWN}
    assert len([q for q in target.requests if q["path"] == "/agents"]) == 1
    assert json.loads(ledger.requests[-1]["body"])["payload"]["status"] == UNKNOWN
    assert "Zq7" not in json.dumps(r) and "Zq7" not in ledger.requests[-1]["body"].decode()


@pytest.mark.parametrize("status", [301, 302, 400, 401, 403, 404, 409, 422, 429])
def test_a_definite_refusal_on_a_write_keeps_the_plain_status(two, status):
    target, ledger = two
    target.routes[("POST", "/agents")] = (status, {}, {})
    r = write_disp(target, ledger).call("agent_registry_create_agent", REGISTER)
    assert r == {"status": "error", "error": f"agent-registry returned {status}"}
    assert json.loads(ledger.requests[-1]["body"])["payload"]["status"] == f"agent-registry returned {status}"


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_a_5xx_on_a_read_keeps_the_plain_status(two, status):
    target, ledger = two
    target.routes[("GET", "/agents")] = (status, {}, {})
    assert write_disp(target, ledger).call("agent_registry_list_agents", {}) == {
        "status": "error", "error": f"agent-registry returned {status}"}


@pytest.mark.parametrize("status", [500, 503])
def test_a_5xx_when_the_ledger_append_fails_keeps_the_audit_refusal_and_sends_nothing(two, status):
    target, ledger = two
    ledger.routes[("POST", "/events")] = (status, {}, {})
    assert write_disp(target, ledger).call("agent_registry_create_agent", REGISTER) == {
        "status": "error", "error": "audit unavailable; no write made"}
    assert not target.requests
