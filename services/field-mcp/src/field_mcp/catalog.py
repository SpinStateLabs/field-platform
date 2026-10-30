"""The reviewed tool surface: which platform routes are tools, and which are excluded and why.

Every route of every service is in exactly one of ``TOOLS`` or ``EXCLUDED``; ``tests/test_route_coverage.py`` builds each
service's app and fails on a route that is in neither, on an entry for a route that no longer exists, and on a route in
both. A new route therefore turns the suite red until someone decides here.

Tier 1 is read-only: every GET, plus seven POSTs that the service code was read to compute and return only
(``READ_ONLY_POSTS``). Tier 2 (state-changing; only the write process offers it, with audit, rate limit and a reason) is the ``tier=2`` entries. Tier 3 (destructive or irreversible)
is never in this server (Don, 2026-10-30).
"""
from __future__ import annotations

from typing import NamedTuple


class Tool(NamedTuple):
    service: str
    method: str
    path: str
    action: str
    effect: str          # first line of the tool description (the blast radius); fixed text, never taken from a service
    tier: int = 1
    drop: tuple[str, ...] = ()                    # parameters of the route this server never offers (Tier 2)
    body_only: tuple[str, ...] | None = None      # the only body properties this server offers (Tier 2)

    @property
    def name(self) -> str:
        return f"{self.service.replace('-', '_')}_{self.action}"


R = "READ-ONLY: no state change."
_POST_READ = "READ-ONLY: computes and returns; the service holds no state change for this route."

TOOLS: tuple[Tool, ...] = (
    Tool("agent-registry", "GET", "/health", "health", R),
    Tool("agent-registry", "GET", "/agents", "list_agents", R),
    Tool("agent-registry", "GET", "/agents/{agent_id}", "get_agent", R),
    Tool("attestation-reporter", "GET", "/health", "health", R),
    Tool("attestation-reporter", "GET", "/pack", "pack", R),
    Tool("attestation-reporter", "GET", "/pack.html", "pack_html", R),
    Tool("claude-approver", "GET", "/health", "health", R),
    Tool("claude-approver", "GET", "/stats", "stats", R),
    Tool("compliance-crosswalk", "GET", "/health", "health", R),
    Tool("compliance-crosswalk", "GET", "/frameworks", "frameworks", R),
    Tool("compliance-crosswalk", "GET", "/controls", "controls", R),
    Tool("compliance-crosswalk", "GET", "/staleness", "staleness", R),
    Tool("compliance-crosswalk", "POST", "/crosswalk", "crosswalk", _POST_READ),
    Tool("compliance-crosswalk", "POST", "/crosswalk/markdown", "crosswalk_markdown", _POST_READ),
    Tool("compliance-crosswalk", "POST", "/pack", "pack", _POST_READ),
    Tool("conformance-sentinel", "GET", "/health", "health", R),
    Tool("conformance-sentinel", "GET", "/clauses", "clauses", R),
    Tool("delegation-authority", "GET", "/health", "health", R),
    Tool("delegation-authority", "GET", "/tokens", "list_tokens", R),
    Tool("delegation-authority", "GET", "/tokens/{token_id}", "get_token", R),
    Tool("delegation-authority", "POST", "/introspect", "introspect", _POST_READ),
    Tool("delegation-authority", "POST", "/oauth/introspect", "oauth_introspect", _POST_READ),
    Tool("federation-broker", "GET", "/health", "health", R),
    Tool("federation-broker", "GET", "/contracts", "list_contracts", R),
    Tool("force-gateway", "GET", "/health", "health", R),
    Tool("force-gateway", "GET", "/presets", "list_presets", R),
    Tool("force-gateway", "GET", "/presets/{name}", "get_preset", R),
    Tool("force-gateway", "GET", "/telemetry", "telemetry", R),
    Tool("incident-replay", "GET", "/health", "health", R),
    Tool("incident-replay", "POST", "/replay", "replay", _POST_READ),
    Tool("incident-replay", "POST", "/replay/markdown", "replay_markdown", _POST_READ),
    Tool("kill-switch", "GET", "/health", "health", R),
    Tool("kill-switch", "GET", "/heartbeat/{agent_id}", "get_heartbeat", R),
    Tool("kill-switch", "GET", "/liveness", "liveness", R),
    Tool("lifecycle-manager", "GET", "/health", "health", R),
    Tool("lifecycle-manager", "GET", "/findings", "findings", R),
    Tool("sealed-ledger", "GET", "/health", "health", R),
    Tool("sealed-ledger", "GET", "/events", "list_events", R),
    Tool("sealed-ledger", "GET", "/verify", "verify", R),
    Tool("sealed-ledger", "GET", "/hold", "get_hold", R),
    Tool("sealed-ledger", "GET", "/retention/check", "retention_check", R),
    Tool("spend-governor", "GET", "/health", "health", R),
    Tool("spend-governor", "GET", "/caps/{agent_id}", "get_cap", R),
    Tool("spend-governor", "GET", "/escalations", "list_escalations", R),
    Tool("spend-governor", "GET", "/policies/{agent_id}", "get_policy", R),
    Tool("spend-governor", "GET", "/rate-limits/{agent_id}", "get_rate_limits", R),
    Tool("spend-governor", "GET", "/status/{agent_id}", "get_status", R),
    Tool("spend-governor", "GET", "/totals/{agent_id}", "get_totals", R),
    Tool("spend-governor", "GET", "/usage/{agent_id}", "get_usage", R),
)


#: Tier 2: state-changing routes. Each effect line is the blast radius shown to the model.
W = "WRITES (Tier 2)"
TOOLS_TIER2: tuple[Tool, ...] = (
    Tool("conformance-sentinel", "POST", "/check", "check",
         W + ": records a verdict on the sealed ledger and counts one action against the agent's spend windows "
         "(also in log-only mode); not reversible.", 2),
    Tool("compliance-crosswalk", "POST", "/regwatch/check", "regwatch_check",
         W + ": fetches the cited regulatory sources and may set stale flags that block evidence packs until a human "
         "clears them; the flags cannot be cleared from here.", 2),
    Tool("agent-registry", "POST", "/agents", "create_agent",
         W + ": registers a new agent record (and its manifest reference); the record stays until it is decommissioned "
         "by a human.", 2),
    Tool("agent-registry", "PATCH", "/agents/{agent_id}", "rename_agent",
         W + ": changes the display name of one agent record only; status, owner, domain and manifest_ref are not "
         "offered (a status change is a kill, revive or decommission).", 2, body_only=("name",)),
    Tool("agent-registry", "POST", "/discover", "discover",
         W + ": scans text you supply for unregistered agents and credentials; the supplied text is sent to the "
         "registry, so never pass real secrets.", 2),
    Tool("federation-broker", "POST", "/crossing", "crossing",
         W + ": decides a cross-organisation crossing and records the verdict on the sealed ledger; not reversible.", 2),
    Tool("sealed-ledger", "POST", "/export", "export",
         W + ": writes an auditor export bundle to the ledger host's default export directory; the directory cannot "
         "be chosen from here.", 2, drop=("out_dir",)),
)
TOOLS = TOOLS + TOOLS_TIER2

#: POSTs that are tools in Tier 1. Any other non-GET in ``TOOLS`` fails a test.
READ_ONLY_POSTS = frozenset({
    ("compliance-crosswalk", "/crosswalk"), ("compliance-crosswalk", "/crosswalk/markdown"),
    ("compliance-crosswalk", "/pack"), ("incident-replay", "/replay"), ("incident-replay", "/replay/markdown"),
    ("delegation-authority", "/introspect"), ("delegation-authority", "/oauth/introspect"),
})

#: Routes that take a form-encoded body (no OpenAPI request body): tool property -> form field.
FORM_BODIES = {("delegation-authority", "/oauth/introspect"): {"token_id": "token"}}

#: Console routes: the console fronts the services above, so the services are exposed directly and never both.
_CONSOLE = "ops-console fronts the services; the owning service's tool is the one path (Don, 2026-10-30)"
_T3 = "Tier 3 (destructive or irreversible); never in this server, CLI and console only (Don, 2026-10-30)"
_OPERATOR = ("key-rotation internals (hash oracle and key fingerprints): not an operator API, loopback-only by design "
             "(field_core/operator_health.py), found by the coverage test, not in Don's route list")

_EXCLUDED_ROUTES: tuple[tuple[str, str, str, str], ...] = (
    # Tier 2
    ("agent-registry", "POST", "/agents/{agent_id}/attest",
     "records a HUMAN re-attestation (attested_by names a human, agent_registry/api.py:92-102); a model must not "
     "record it. Tier 3 candidate, awaiting Don's ruling"),
    # Tier 3
    ("kill-switch", "POST", "/kill/{agent_id}", _T3),
    ("kill-switch", "POST", "/kill/domain/{domain}", _T3),
    ("kill-switch", "POST", "/revive/{agent_id}", _T3),
    ("kill-switch", "POST", "/drill/{agent_id}", _T3 + "; a drill flips agent status"),
    ("kill-switch", "POST", "/heartbeat/{agent_id}", _T3 + "; a forged heartbeat masks a dead agent"),
    ("delegation-authority", "POST", "/tokens", _T3),
    ("delegation-authority", "POST", "/tokens/{token_id}/revoke", _T3),
    ("sealed-ledger", "POST", "/events", _T3 + "; append-only"),
    ("sealed-ledger", "POST", "/rotate", _T3),
    ("sealed-ledger", "POST", "/hold", _T3),
    ("sealed-ledger", "POST", "/hold/release", _T3),
    ("sealed-ledger", "POST", "/retention/apply", _T3 + "; deletes expired ledger data"),
    ("spend-governor", "PUT", "/caps/{agent_id}", _T3),
    ("spend-governor", "PUT", "/policies/{agent_id}", _T3),
    ("spend-governor", "PUT", "/rate-limits/{agent_id}", _T3),
    ("spend-governor", "POST", "/spend", _T3 + "; forged counters can trigger cap breaches"),
    ("spend-governor", "POST", "/usage", _T3 + "; forged counters can trigger cap breaches"),
    ("spend-governor", "POST", "/escalations/{escalation_id}/resolve", _T3 + "; a human approval"),
    ("federation-broker", "PUT", "/contracts/{contract_id}", _T3),
    ("lifecycle-manager", "POST", "/sweep", _T3 + "; auto_kill_orphans halts agents"),
    # Other
    ("claude-approver", "POST", "/halt/{field_agent_id}",
     "open path by design (no x-field-auth), the kill-switch's outbound target, not an operator API"),
    ("force-gateway", "POST", "/v1/messages", "a paid model call proxied for agents, not an operator action"),
    ("ops-console", "GET", "/", _CONSOLE), ("ops-console", "GET", "/health", _CONSOLE),
    ("ops-console", "GET", "/api/overview", _CONSOLE), ("ops-console", "GET", "/api/platform", _CONSOLE),
    ("ops-console", "GET", "/api/agents/{agent_id}", _CONSOLE),
    ("ops-console", "GET", "/api/agents/{agent_id}/manifest", _CONSOLE),
    ("ops-console", "GET", "/api/events", _CONSOLE), ("ops-console", "GET", "/api/events/export", _CONSOLE),
    ("ops-console", "GET", "/api/stream", _CONSOLE),
    ("ops-console", "POST", "/api/agents/{agent_id}/drill", _CONSOLE),
    ("ops-console", "POST", "/api/agents/{agent_id}/kill", _CONSOLE),
    ("ops-console", "POST", "/api/agents/{agent_id}/revive", _CONSOLE),
    ("ops-console", "POST", "/api/agents/bulk", _CONSOLE + "; a bulk tool would bypass per-call review"),
    ("ops-console", "POST", "/api/check", _CONSOLE),
    ("ops-console", "POST", "/api/escalations/{escalation_id}/resolve", _CONSOLE),
    ("ops-console", "POST", "/api/fleet/halt", _CONSOLE),
    ("ops-console", "POST", "/api/tokens/{token_id}/revoke", _CONSOLE),
) + tuple(
    (svc, m, p, _OPERATOR)
    for svc in ("agent-registry", "delegation-authority", "federation-broker", "kill-switch",
                "lifecycle-manager", "ops-console", "sealed-ledger", "spend-governor")
    for m, p in (("GET", "/operator/rotation-state"), ("POST", "/operator/verify-hash"))
)

EXCLUDED: dict[tuple[str, str, str], str] = {(s, m, p): why for s, m, p, why in _EXCLUDED_ROUTES}

#: FastAPI's own documentation routes: not platform routes.
FRAMEWORK_PATHS = frozenset({"/docs", "/openapi.json", "/redoc", "/docs/oauth2-redirect"})

SERVICES = tuple(sorted({t.service for t in TOOLS} | {k[0] for k in EXCLUDED}))
