"""Load and sanity-check the agent's FIELD manifest sketch (stdlib + PyYAML).

This is NOT the FIELD validator (``field validate`` / field_core, which the tests
run separately); it checks the few things the agent's own code depends on and
that ADR-0079 section 3 pins: the agent name, a ``delegation.scope`` that stays
inside the ADR ceiling and omits every deliberately-absent scope, a kill switch
with a ``local_sentinel`` and ``sentinel_max_age_s``, a spend cap with
``on_breach: halt``, and a named grantor. It returns the scope the refuse list
compares against.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import AGENT_NAME
from .actions import ADR_SCOPE, ActionKind

#: ADR-0079 section 3: "deliberately absent (so any attempt is a scope BLOCK)"
FORBIDDEN_SCOPE = frozenset(
    k.value
    for k in (
        ActionKind.MINT_DELEGATION_TOKEN,
        ActionKind.EDIT_DOA_ROSTER,
        ActionKind.EDIT_MANIFEST,
        ActionKind.READ_SECRET,
        ActionKind.DISABLE_KILL_SWITCH,
    )
)
MAX_TTL_DAYS = 30


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class AgentManifest:
    name: str
    scope: frozenset[str]
    granted_by: str
    expiry: str
    local_sentinel: str
    sentinel_max_age_s: int


def _get(d: Any, *path: str) -> Any:
    for p in path:
        if not isinstance(d, dict) or p not in d:
            raise ManifestError("missing " + ".".join(path))
        d = d[p]
    return d


def load_manifest(path: str | Path) -> AgentManifest:
    p = Path(path)
    if not p.is_file():
        raise ManifestError(f"no manifest at {p}")
    try:
        doc = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ManifestError(f"manifest is not valid YAML: {type(exc).__name__}") from None
    name = _get(doc, "agent", "name")
    if name != AGENT_NAME:
        raise ManifestError(f"agent.name must be {AGENT_NAME}")
    scope = _get(doc, "delegation", "scope")
    if not isinstance(scope, list) or not all(isinstance(s, str) for s in scope):
        raise ManifestError("delegation.scope must be a list of strings")
    scope_set = frozenset(scope)
    if scope_set & FORBIDDEN_SCOPE:
        raise ManifestError("delegation.scope contains a deliberately-absent scope: " + ", ".join(sorted(scope_set & FORBIDDEN_SCOPE)))
    if scope_set - ADR_SCOPE:
        raise ManifestError("delegation.scope is wider than the ADR-0079 ceiling: " + ", ".join(sorted(scope_set - ADR_SCOPE)))
    ks = _get(doc, "enforcement", "kill_switch")
    sentinel = ks.get("local_sentinel")
    age = ks.get("sentinel_max_age_s")
    if not sentinel or not isinstance(age, int) or isinstance(age, bool) or age < 1:
        raise ManifestError("kill_switch needs local_sentinel and sentinel_max_age_s (a dead watcher is fail-open without it)")
    if _get(doc, "enforcement", "spend_cap", "on_breach") != "halt":
        raise ManifestError("spend_cap.on_breach must be halt")
    granted_by = _get(doc, "delegation", "granted_by")
    if not isinstance(granted_by, str) or not granted_by.strip():
        raise ManifestError("delegation.granted_by must name a human")
    return AgentManifest(name, scope_set, granted_by, str(_get(doc, "delegation", "expiry")), str(sentinel), age)
