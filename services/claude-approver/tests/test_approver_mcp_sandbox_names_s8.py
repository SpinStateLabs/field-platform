"""S8-17 — an ``agent.mcp_tool_use`` named bash, write or edit is an MCP server's tool, not the agent's
built-in sandbox: it is checked under its OWN name (the sentinel BLOCKs D.scope unless that name is in
scope), never as ``run commands in sandbox``. Explicit maps still win for both event types."""

from __future__ import annotations

import json

import pytest

from approver_fakes import CONSOLE_AGENT, default_map, set_map
from claude_approver import config
from claude_approver.config import MCP_TOOL_USE, SANDBOX_ACTION, AgentEntry, ToolMap

SID = "sesn_01"
MCP = {"etype": "agent.mcp_tool_use"}


def _pending(console, *asks):
    console.add_session(SID, CONSOLE_AGENT)
    evs = [console.ask(SID, name, **kw) for name, kw in asks]
    console.idle(SID, event_ids=[e.id for e in evs])
    return evs


@pytest.mark.parametrize("name", ["bash", "write", "edit"])
def test_an_mcp_tool_with_a_builtin_name_is_checked_under_its_own_name(console, field, make_approver, mapped, name):
    _pending(console, (name, MCP))
    make_approver().tick()
    (check,) = field.checks()
    assert check["action"] == name != SANDBOX_ACTION
    assert check["context"]["event_type"] == MCP_TOOL_USE


def test_a_builtin_with_the_same_names_is_still_the_sandbox_action(console, field, make_approver, mapped):
    _pending(console, ("bash", {}), ("write", {}), ("edit", {}))
    make_approver().tick()
    assert [c["action"] for c in field.checks()] == [SANDBOX_ACTION] * 3


def test_builtin_and_mcp_in_one_session_are_told_apart(console, field, make_approver, mapped):
    _pending(console, ("bash", {}), ("bash", MCP))
    make_approver().tick()
    assert [c["action"] for c in field.checks()] == [SANDBOX_ACTION, "bash"]


def test_the_explicit_maps_still_apply_to_an_mcp_tool(console, field, make_approver, monkeypatch):
    set_map(monkeypatch, default_map(actions={"edit": "edit a ticket"}))
    monkeypatch.setenv("CLAUDE_APPROVER_TOOL_MAP", json.dumps({"write": "global write"}))
    _pending(console, ("edit", MCP), ("write", MCP), ("bash", MCP))
    make_approver().tick()
    assert [c["action"] for c in field.checks()] == ["edit a ticket", "global write", "bash"]


def _entry(**actions) -> AgentEntry:
    return AgentEntry(console_agent_id="a", field_agent_id="f", token_id="t", actions=actions)


@pytest.mark.parametrize("etype, want", [
    (None, SANDBOX_ACTION),                    # legacy callers: unchanged
    ("agent.tool_use", SANDBOX_ACTION),
    (MCP_TOOL_USE, "bash"),
    ("something.else", SANDBOX_ACTION),        # only the MCP type opts out
])
def test_resolve_action_direct(etype, want):
    assert config.resolve_action("bash", _entry(), ToolMap({}), etype) == want


def test_resolve_action_without_the_new_argument_is_unchanged():
    assert config.resolve_action("bash", _entry(), ToolMap({})) == SANDBOX_ACTION
    assert config.resolve_action("glob", _entry(), ToolMap({})) == "glob"
