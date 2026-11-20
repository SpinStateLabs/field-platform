"""Tests for the merge of PR 368 (Tier 1) into the Tier 2 branch.

After the merge three layers refuse a bad Tier 2 agent id: the tool schema's pattern, PR 368's single-segment check
(``check_body_ids``, run in ``_call`` for every tier) and ``_write``'s own registry-rule check. Each of the first two
catches everything the third does, so mutant ID3 (the third removed) survived every test that goes through ``call``.
This test calls ``_write`` directly, with the other two layers out of the way, and pins the third on its own.
"""
import json

import pytest

from field_mcp.client import ToolError
from test_pr380_conditions_c1065 import CHECK
from test_tier2 import two, write_disp   # noqa: F401  (``two`` is a fixture)


@pytest.mark.parametrize("bad", ["agent-1\n", "Agent1", "-agent", "a" * 201, "agent 1"])
def test_the_writes_own_agent_id_check_stands_alone(two, bad):
    target, ledger = two
    d = write_disp(target, ledger)
    tool = d.specs["conformance_sentinel_check"].tool
    args = json.loads(json.dumps(CHECK))
    args["body"]["agent_id"] = bad
    with pytest.raises(ToolError, match="arguments refused"):
        d._write(tool, d.upstreams[tool.service], "/check", {}, args)
    assert not target.requests and not ledger.requests        # nothing sent, no intent row


def test_a_good_agent_id_passes_the_writes_own_check(two):
    target, ledger = two
    d = write_disp(target, ledger)
    tool = d.specs["conformance_sentinel_check"].tool
    args = json.loads(json.dumps(CHECK))
    args["body"]["agent_id"] = "agent-1"
    assert d._write(tool, d.upstreams[tool.service], "/check", {}, args)["status"] == "ok"
