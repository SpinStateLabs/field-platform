"""Configuration, read from the environment per call (so a rotated key, a
rewritten agent map or a moved secret file is honoured on the next poll).

Nothing in this module ever returns, logs or raises with the CONTENT of a key
or secret file: readers return the value or ``None``, and error strings name
the variable, never the value.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_KEY_FILE = "/run/claude-approver/api-key"
DEFAULT_POLL_SECONDS = 2.0
#: Floor on the poll interval: 0 would spin against the 600 RPM org limit.
MIN_POLL_SECONDS = 0.5
DEFAULT_HALT_WAIT_SECONDS = 20.0

#: Built-in tools that act inside the sandbox map to this one FIELD scope
#: string (Don's P27 decision 5: a ``bash`` call is one scope string, not a
#: classified action).
SANDBOX_ACTION = "run commands in sandbox"
SANDBOX_TOOLS = frozenset({"bash", "write", "edit"})

ENV_KEY_FILE = "CLAUDE_APPROVER_API_KEY_FILE"
ENV_AGENT_MAP = "CLAUDE_APPROVER_AGENT_MAP"
ENV_AGENT_MAP_FILE = "CLAUDE_APPROVER_AGENT_MAP_FILE"
ENV_TOOL_MAP = "CLAUDE_APPROVER_TOOL_MAP"
ENV_POLL = "CLAUDE_APPROVER_POLL_SECONDS"
ENV_ENVIRONMENT = "CLAUDE_APPROVER_ENVIRONMENT_ID"
ENV_HALT_WAIT = "CLAUDE_APPROVER_HALT_WAIT_SECONDS"


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def poll_seconds() -> float:
    return max(MIN_POLL_SECONDS, _float_env(ENV_POLL, DEFAULT_POLL_SECONDS))


def halt_wait_seconds() -> float:
    return _float_env(ENV_HALT_WAIT, DEFAULT_HALT_WAIT_SECONDS)


def environment_filter() -> str | None:
    return os.environ.get(ENV_ENVIRONMENT, "").strip() or None


def key_file_path() -> Path:
    return Path(os.environ.get(ENV_KEY_FILE, "").strip() or DEFAULT_KEY_FILE)


def read_secret_file(path: str | Path) -> str | None:
    """The trimmed content of a secret file, or ``None`` when it is missing,
    unreadable, not UTF-8 or blank. Never raises; never says why in a way that
    could carry the content."""
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    text = text.strip()
    return text or None


def read_api_key() -> str | None:
    return read_secret_file(key_file_path())


def key_file_present() -> bool:
    return read_api_key() is not None


def service_url(env_var: str, default: str) -> str:
    return (os.environ.get(env_var, "").strip() or default).rstrip("/")


def sentinel_url() -> str:
    return service_url("FIELD_SENTINEL_URL", "http://127.0.0.1:8004")


def killswitch_url() -> str:
    return service_url("FIELD_KILLSWITCH_URL", "http://127.0.0.1:8005")


def governor_url() -> str:
    return service_url("FIELD_GOVERNOR_URL", "http://127.0.0.1:8006")


def data_dir() -> Path:
    return Path(os.environ.get("FIELD_DATA_DIR", "").strip() or "./var")


# --------------------------------------------------------------------------
# Agent map
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentEntry:
    """One Console agent's FIELD identity.

    ``problem`` is set when the entry is present but unusable (no
    ``field_agent_id``, wrong types, a bad ``estate_base_url``). Such an
    agent's ``ask`` calls are DENIED (reason class ``unmapped``) and nothing
    else happens for it: no sentinel call, no heartbeat, no usage post."""

    console_agent_id: str
    field_agent_id: str | None
    token_id: str | None = None
    actions: dict[str, str] = field(default_factory=dict)
    custom_tools: dict[str, str] = field(default_factory=dict)
    estate_base_url: str | None = None
    secret_file: str | None = None
    problem: str | None = None


@dataclass(frozen=True)
class AgentMap:
    entries: dict[str, AgentEntry]
    error: str | None = None

    def consoles_for(self, field_agent_id: str) -> list[str]:
        return [
            cid for cid, e in self.entries.items()
            if e.problem is None and e.field_agent_id == field_agent_id
        ]

    def field_ids(self) -> set[str]:
        return {
            e.field_agent_id for e in self.entries.values()
            if e.problem is None and e.field_agent_id
        }


def _str_map(value: object) -> dict[str, str] | None:
    if value is None:
        return {}
    if not isinstance(value, dict):
        return None
    out: dict[str, str] = {}
    for k, v in value.items():
        if not isinstance(k, str) or not isinstance(v, str) or not v.strip():
            return None
        out[k] = v
    return out


def _parse_entry(console_id: str, raw: object) -> AgentEntry:
    def bad(problem: str) -> AgentEntry:
        return AgentEntry(console_agent_id=console_id, field_agent_id=None, problem=problem)

    if not isinstance(raw, dict):
        return bad("entry is not a JSON object")
    fid = raw.get("field_agent_id")
    if not isinstance(fid, str) or not fid.strip():
        return bad("entry has no field_agent_id")
    token = raw.get("token_id")
    if token is not None and not isinstance(token, str):
        return bad("token_id is not a string")
    actions = _str_map(raw.get("actions"))
    if actions is None:
        return bad("actions is not an object of non-empty strings")
    customs = _str_map(raw.get("custom_tools"))
    if customs is None:
        return bad("custom_tools is not an object of non-empty strings")
    base = raw.get("estate_base_url")
    if base is not None:
        if not isinstance(base, str):
            return bad("estate_base_url is not a string")
        base = base.strip().rstrip("/") or None
        if base is not None:
            parts = urlsplit(base)
            if parts.scheme not in ("http", "https") or not parts.hostname:
                return bad("estate_base_url is not an http(s) URL")
            # a credential in the URL would reach httpx's request log on every call;
            # the perimeter secret belongs in secret_file
            if parts.username is not None or parts.password is not None:
                return bad("estate_base_url must not carry credentials")
    secret_file = raw.get("secret_file")
    if secret_file is not None:
        if not isinstance(secret_file, str):
            return bad("secret_file is not a string")
        secret_file = secret_file.strip() or None
    return AgentEntry(
        console_agent_id=console_id,
        field_agent_id=fid.strip(),
        token_id=token or None,
        actions=actions,
        custom_tools=customs,
        estate_base_url=base,
        secret_file=secret_file,
    )


def parse_agent_map(text: str) -> AgentMap:
    """Parse the JSON map. Structural garbage empties the WHOLE map (nothing
    is touched, error reported on ``/stats``); a single bad entry is kept as
    an unusable entry whose calls are denied."""
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        return AgentMap({}, error="agent map is not valid JSON")
    if not isinstance(data, dict):
        return AgentMap({}, error="agent map is not a JSON object")
    entries: dict[str, AgentEntry] = {}
    for key, raw in data.items():
        if not isinstance(key, str) or key.startswith("_"):
            continue
        if not key.strip():
            return AgentMap({}, error="agent map has a blank console agent id")
        entries[key] = _parse_entry(key, raw)
    return AgentMap(entries)


def load_agent_map() -> AgentMap:
    """``CLAUDE_APPROVER_AGENT_MAP_FILE`` (a path) wins; else
    ``CLAUDE_APPROVER_AGENT_MAP`` is a path when it names an existing file,
    otherwise inline JSON. Unset => empty map (the approver touches nothing)."""
    path = os.environ.get(ENV_AGENT_MAP_FILE, "").strip()
    raw = os.environ.get(ENV_AGENT_MAP, "").strip()
    if not path and raw and not raw.lstrip().startswith("{"):
        try:
            if Path(raw).is_file():
                path = raw
        except (OSError, ValueError):
            pass
    if path:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, ValueError):
            return AgentMap({}, error="agent map file is unreadable")
        return parse_agent_map(text)
    if not raw:
        return AgentMap({})
    return parse_agent_map(raw)


@dataclass(frozen=True)
class ToolMap:
    entries: dict[str, str]
    error: str | None = None


def load_tool_map() -> ToolMap:
    raw = os.environ.get(ENV_TOOL_MAP, "").strip()
    if not raw:
        return ToolMap({})
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return ToolMap({}, error="CLAUDE_APPROVER_TOOL_MAP is not valid JSON")
    parsed = _str_map(data)
    if parsed is None:
        return ToolMap({}, error="CLAUDE_APPROVER_TOOL_MAP is not an object of non-empty strings")
    return ToolMap(parsed)


def resolve_action(tool_name: str, entry: AgentEntry, tool_map: ToolMap) -> str:
    """Per-agent ``actions`` > global ``CLAUDE_APPROVER_TOOL_MAP`` > built-in
    default (``bash``/``write``/``edit`` -> ``run commands in sandbox``;
    anything else, MCP tools included, -> its own name, which the sentinel
    BLOCKs ``D.scope`` unless it is in scope: fail closed by construction)."""
    if tool_name in entry.actions:
        return entry.actions[tool_name]
    if tool_name in tool_map.entries:
        return tool_map.entries[tool_name]
    if tool_name in SANDBOX_TOOLS:
        return SANDBOX_ACTION
    return tool_name
