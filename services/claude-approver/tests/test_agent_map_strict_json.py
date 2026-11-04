"""S3-9: the agent map and the tool map are parsed strictly. A repeated JSON key (at any depth) or NaN/Infinity takes
the existing fail-closed branch (an empty map with an error, so nothing is touched and /stats shows it); plain
`json.loads` kept the last of two entries silently, so an operator reading the first saw a different policy."""

from __future__ import annotations

import pytest

from claude_approver import config

ENTRY = '{"field_agent_id": "fa-1", "token_id": "t1"}'


def test_a_clean_agent_map_still_parses():
    m = config.parse_agent_map('{"agent-a": %s, "agent-b": {"field_agent_id": "fa-2"}}' % ENTRY)
    assert m.error is None and set(m.entries) == {"agent-a", "agent-b"}
    assert m.entries["agent-a"].field_agent_id == "fa-1"


@pytest.mark.parametrize("text", [
    '{"agent-a": %s, "agent-a": {"field_agent_id": "fa-9"}}' % ENTRY,             # one console id twice
    '{"agent-a": {"field_agent_id": "fa-1", "field_agent_id": "fa-2"}}',          # a key twice inside one entry
    '{"agent-a": {"field_agent_id": "fa-1", "actions": {"bash": "x", "bash": "y"}}}',   # nested, any depth
    '{"_comment": 1, "_comment": 2, "agent-a": %s}' % ENTRY,                      # even a skipped comment key
], ids=["console-id", "inside-entry", "nested", "comment-key"])
def test_a_duplicate_key_empties_the_map_with_a_named_error(text):
    m = config.parse_agent_map(text)
    assert m.entries == {} and m.error == "agent map has a duplicate key"


@pytest.mark.parametrize("const", ["NaN", "Infinity", "-Infinity"])
def test_a_non_standard_constant_is_refused_fail_closed(const):
    m = config.parse_agent_map('{"agent-a": {"field_agent_id": "fa-1", "ttl": %s}}' % const)
    assert m.entries == {} and m.error == "agent map is not valid JSON"


def test_the_error_never_echoes_the_duplicated_key():
    m = config.parse_agent_map('{"SECRET-id": %s, "SECRET-id": %s}' % (ENTRY, ENTRY))
    assert "SECRET" not in (m.error or "")


def test_a_clean_tool_map_still_loads(monkeypatch):
    monkeypatch.setenv(config.ENV_TOOL_MAP, '{"bash": "run it", "web": "browse"}')
    t = config.load_tool_map()
    assert t.error is None and t.entries == {"bash": "run it", "web": "browse"}


def test_a_duplicate_tool_name_is_refused_fail_closed(monkeypatch):
    monkeypatch.setenv(config.ENV_TOOL_MAP, '{"bash": "run it", "bash": "something else"}')
    t = config.load_tool_map()
    assert t.entries == {} and t.error == "CLAUDE_APPROVER_TOOL_MAP has a duplicate key"


def test_nan_in_the_tool_map_is_refused(monkeypatch):
    monkeypatch.setenv(config.ENV_TOOL_MAP, '{"bash": NaN}')
    t = config.load_tool_map()
    assert t.entries == {} and t.error == "CLAUDE_APPROVER_TOOL_MAP is not valid JSON"


def test_the_inline_and_file_paths_both_refuse_a_duplicate(monkeypatch, tmp_path):
    dup = '{"agent-a": %s, "agent-a": %s}' % (ENTRY, ENTRY)
    for n in (config.ENV_AGENT_MAP, config.ENV_AGENT_MAP_FILE):
        monkeypatch.delenv(n, raising=False)
    monkeypatch.setenv(config.ENV_AGENT_MAP, dup)
    assert config.load_agent_map().error == "agent map has a duplicate key"
    monkeypatch.delenv(config.ENV_AGENT_MAP)
    f = tmp_path / "map.json"
    f.write_text(dup, encoding="utf-8")
    monkeypatch.setenv(config.ENV_AGENT_MAP_FILE, str(f))
    assert config.load_agent_map().error == "agent map has a duplicate key"
