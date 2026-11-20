"""C-1083 (reviewer C-775 F-C775-1, Q-49): a body or form id that a service puts into a URL is one path segment.

The three crosswalk POST tools, the two replay tools and the two introspect tools take `agent_id` or `token_id` in the
request body (or form). On the C-835 head only PATH arguments carried the segment pattern, so a body
`agent_id` of `x/../../operator/rotation-state` passed validation and reached the service, which builds URLs from it.
Now every top-level body property and form field whose name ends in `id` carries the single-segment pattern in the tool
schema AND is checked with `SEGMENT.fullmatch` before any request (mutants D6 runtime check gone, D7 schema pattern gone).
Nested objects (a manifest) are the service's own schema and are not walked: stated limit.
"""
import pytest

from conftest import KEY, config_for
from field_mcp import client as cl
from field_mcp.tools import Dispatcher, build_specs, check_body_ids

SVCS = ("compliance-crosswalk", "incident-replay", "delegation-authority")
BAD = ["a/b", "..", ".", "a?b", "a#b", "x/../../operator/rotation-state", "a\n", "%2e%2e", "a b", "", "x" * 201]
CALLS = {
    "compliance_crosswalk_pack": lambda v: {"body": {"signer": "s", "manifest": {}, "agent_id": v}},
    "compliance_crosswalk_crosswalk": lambda v: {"body": {"manifest": {}, "agent_id": v}},
    "compliance_crosswalk_crosswalk_markdown": lambda v: {"body": {"manifest": {}, "agent_id": v}},
    "incident_replay_replay": lambda v: {"body": {"agent_id": v, "since": "2026-01-01T00:00:00Z", "until": "2026-01-02T00:00:00Z"}},
    "incident_replay_replay_markdown": lambda v: {"body": {"agent_id": v, "since": "2026-01-01T00:00:00Z", "until": "2026-01-02T00:00:00Z"}},
    "delegation_authority_introspect": lambda v: {"body": {"token_id": v}},
    "delegation_authority_oauth_introspect": lambda v: {"token_id": v},
}


def disp(stub):
    cfg = config_for(stub, *SVCS)
    return Dispatcher(cfg, {s: cl.Upstream(s, stub.base, KEY) for s in cfg.services})


@pytest.mark.parametrize("tool", sorted(CALLS))
@pytest.mark.parametrize("bad", BAD)
def test_a_body_or_form_id_that_is_not_one_segment_is_refused_before_any_request(stub, tool, bad):
    r = disp(stub).call(tool, CALLS[tool](bad))
    assert r["status"] == "error" and (bad == "" or bad not in str(r))
    assert not stub.requests


@pytest.mark.parametrize("tool", sorted(CALLS))
def test_a_plain_id_still_reaches_the_service_unchanged(stub, tool):
    r = disp(stub).call(tool, CALLS[tool]("agent-1"))
    assert r["status"] == "ok" and len(stub.requests) == 1
    assert b"agent-1" in stub.requests[0]["body"]


def test_a_null_crosswalk_agent_id_is_still_allowed(stub):
    assert disp(stub).call("compliance_crosswalk_crosswalk", {"body": {"manifest": {}, "agent_id": None}})["status"] == "ok"


def test_the_tool_schemas_carry_the_segment_pattern_on_body_and_form_ids():
    specs = {s.name: s for s in build_specs(1)}
    body = specs["compliance_crosswalk_pack"].input_schema["properties"]["body"]["properties"]["agent_id"]
    assert any(b.get("pattern") == cl.SEGMENT.pattern for b in body["anyOf"]), body
    assert specs["incident_replay_replay"].input_schema["properties"]["body"]["properties"]["agent_id"]["pattern"] == cl.SEGMENT.pattern
    assert specs["delegation_authority_introspect"].input_schema["properties"]["body"]["properties"]["token_id"]["pattern"] == cl.SEGMENT.pattern
    assert specs["delegation_authority_oauth_introspect"].input_schema["properties"]["token_id"]["pattern"] == cl.SEGMENT.pattern
    assert "pattern" not in specs["compliance_crosswalk_pack"].input_schema["properties"]["body"]["properties"]["signer"]


@pytest.mark.parametrize("bad", BAD)
def test_check_body_ids_refuses_even_if_the_schema_layer_is_gone(bad):
    with pytest.raises(cl.ToolError):
        check_body_ids({"agent_id": bad}, {})
    with pytest.raises(cl.ToolError):
        check_body_ids(None, {"token_id": bad})


def test_check_body_ids_leaves_non_id_fields_and_nested_objects_alone():
    check_body_ids({"agent_id": "a-1", "signer": "a/b", "manifest": {"id": "x/y"}, "since": "2026-01-01T00:00:00Z"}, {"token_id": "t1"})
    check_body_ids({"agent_id": None}, {})
    check_body_ids("not a dict", {})
