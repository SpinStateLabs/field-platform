"""Build the tool-schema snapshot from the services' own apps (their pydantic models, through FastAPI's OpenAPI).

Used by ``scripts/gen_snapshot.py`` to write ``src/field_mcp/snapshot.json`` and by the drift test to compare it with the
live apps. The server itself never imports a service.
"""
from __future__ import annotations

import importlib
import os
import tempfile
from typing import Any

from field_mcp.catalog import FRAMEWORK_PATHS, FORM_BODIES, TOOLS

MODULES = {"agent-registry": "agent_registry", "attestation-reporter": "attestation_reporter",
           "claude-approver": "claude_approver", "compliance-crosswalk": "compliance_crosswalk",
           "conformance-sentinel": "conformance_sentinel", "delegation-authority": "delegation_authority",
           "federation-broker": "federation_broker", "force-gateway": "force_gateway",
           "incident-replay": "incident_replay", "kill-switch": "kill_switch",
           "lifecycle-manager": "lifecycle_manager", "ops-console": "ops_console",
           "sealed-ledger": "sealed_ledger", "spend-governor": "spend_governor"}


def build_apps() -> dict[str, Any]:
    """Each service's app, built with its defaults in a scratch directory (nothing is requested over the network)."""
    cwd = os.getcwd()
    os.chdir(tempfile.mkdtemp())
    try:
        return {svc: importlib.import_module(mod + ".api").create_app() for svc, mod in MODULES.items()}
    finally:
        os.chdir(cwd)


def live_routes(apps: dict[str, Any]) -> set[tuple[str, str, str]]:
    out = set()
    for svc, app in apps.items():
        for r in app.routes:
            if hasattr(r, "methods") and r.path not in FRAMEWORK_PATHS:
                out.update((svc, m, r.path) for m in r.methods - {"HEAD", "OPTIONS"})
    return out


def _deref(node: Any, comps: dict[str, Any], seen: tuple[str, ...] = ()) -> Any:
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
            name = ref.rsplit("/", 1)[1]
            if name in seen:                       # a recursive model: stop at the reference, keep it an object
                return {"type": "object"}
            return _deref(comps[name], comps, seen + (name,))
        return {k: _deref(v, comps, seen) for k, v in node.items()}
    if isinstance(node, list):
        return [_deref(v, comps, seen) for v in node]
    return node


def build_snapshot(apps: dict[str, Any]) -> dict[str, Any]:
    snap: dict[str, Any] = {}
    for t in TOOLS:
        spec = apps[t.service].openapi()
        op = spec["paths"][t.path][t.method.lower()]
        comps = spec.get("components", {}).get("schemas", {})
        params = [{"name": p["name"], "in": p["in"], "required": bool(p.get("required")),
                   "schema": _deref(p.get("schema", {}), comps)}
                  for p in op.get("parameters", []) if p["in"] in ("path", "query")]
        body = None
        content = (op.get("requestBody") or {}).get("content", {})
        if "application/json" in content:
            body = _deref(content["application/json"].get("schema", {}), comps)
        form = FORM_BODIES.get((t.service, t.path))
        snap[t.name] = {"service": t.service, "method": t.method, "path": t.path,
                        "parameters": sorted(params, key=lambda p: (p["in"], p["name"])),
                        "body": body, "form": sorted(form) if form else None}
    return snap
