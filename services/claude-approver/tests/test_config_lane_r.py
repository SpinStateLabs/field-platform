"""Mutant survivors in claude_approver.config (Lane R)."""

import json

from claude_approver import config
from claude_approver.config import AgentEntry, AgentMap


def test_field_ids_skips_unusable_and_unidentified_entries():
    """field_ids lists only usable entries that carry a field id: an entry
    with a `problem` is denied everywhere, so its id must not be counted."""
    amap = AgentMap({
        "ok": AgentEntry("ok", "field-a"),
        "bad": AgentEntry("bad", "field-b", problem="estate_base_url is not valid"),
        "noid": AgentEntry("noid", None),
        "blank": AgentEntry("blank", ""),
    })
    assert amap.field_ids() == {"field-a"}


def test_agent_map_file_wins_over_an_agent_map_naming_another_file(tmp_path, monkeypatch):
    """Docstring contract: CLAUDE_APPROVER_AGENT_MAP_FILE wins. When the FILE
    var is set, AGENT_MAP naming an existing file must not displace it."""
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps({"console-a": {"field_agent_id": "from-a"}}), encoding="utf-8")
    b.write_text(json.dumps({"console-b": {"field_agent_id": "from-b"}}), encoding="utf-8")
    monkeypatch.setenv(config.ENV_AGENT_MAP_FILE, str(a))
    monkeypatch.setenv(config.ENV_AGENT_MAP, str(b))
    assert list(config.load_agent_map().entries) == ["console-a"]


def test_agent_map_naming_a_file_is_read_when_no_file_var(tmp_path, monkeypatch):
    b = tmp_path / "b.json"
    b.write_text(json.dumps({"console-b": {"field_agent_id": "from-b"}}), encoding="utf-8")
    monkeypatch.delenv(config.ENV_AGENT_MAP_FILE, raising=False)
    monkeypatch.setenv(config.ENV_AGENT_MAP, str(b))
    assert list(config.load_agent_map().entries) == ["console-b"]
