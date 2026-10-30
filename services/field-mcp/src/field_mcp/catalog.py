"""The reviewed tool surface: which platform routes are tools, and which are excluded and why.

Every route of every service is in exactly one of ``TOOLS``, ``WRITE_TOOLS`` or ``EXCLUDED``; ``tests/test_route_coverage.py``
builds each service's app and fails on a route that is in none, on an entry for a route that no longer exists, and on a
route in two. A new route therefore turns the suite red until someone decides here.

Tier 1 is read-only: every GET, plus seven POSTs that the service code was read to compute and return only
(``READ_ONLY_POSTS``). Tier 2 (``WRITE_TOOLS``, 8 tools) changes state: registered only by the write process and only with
FFMCP_ENABLE_WRITES=1. Tier 3 (destructive or irreversible) is never in this server (Don, 2026-10-30).
"""
from __future__ import annotations

from typing import NamedTuple


class Tool(NamedTuple):
    service: str
    method: str
    path: str
    action: str
    effect: str          # first line of the tool description; fixed text, never taken from a service

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

# Tier 2. The first line of each description is ``BLAST RADIUS: <effect>; <reversible|irreversible>`` (no ';' inside the
# effect). Each effect was read against the service code (file:line at the time of writing; tests/test_write_tier.py
# BLAST_EVIDENCE fails if the code it rests on disappears):
#   sentinel /check      conformance_sentinel/engine.py:366-405 (check, _meter, sentinel.metering_gap at 401), SPEC.md:23
#   regwatch/check       compliance_crosswalk/api.py:153-163, regwatch.py:259 default_fetcher, :388-452 run_check (apply_mark :430)
#   POST /agents         agent_registry/api.py:220-240 (registry.registered :235), store.py:140 add; no delete route exists
#   PATCH /agents/{id}   agent_registry/api.py:255-355 (status = kill/revive/retire by another name :257-263, terminal :306,
#                        :320; registry.updated :351); the tool sends ``name`` only (WRITE_BODY_FIELDS)
#   attest               agent_registry/api.py:357-392 (registry.attested :389), store.py:252 attest overwrites the clock
#   discover             agent_registry/api.py:397-413, discover.py:373 (a computation: nothing stored, nothing ledgered)
#   crossing             federation_broker/api.py:94-96, engine.py:377-417 (federation.<decision> ledger row at :407)
#   export               sealed_ledger/api.py:441-486 (bundle written on the ledger host, default <ledger dir>/exports :457)
WRITE_TOOLS: tuple[Tool, ...] = (
    Tool("conformance-sentinel", "POST", "/check", "check",
         "BLAST RADIUS: decides one proposed action, every ALLOW is metered to spend-governor as one action and every "
         "verdict is ledgered, a failed meter writes a sentinel.metering_gap row; irreversible"),
    Tool("compliance-crosswalk", "POST", "/regwatch/check", "regwatch_check",
         "BLAST RADIUS: fetches every cited regulatory source from the crosswalk host, records content hashes and sets "
         "stale flags that block evidence packs until the crosswalk CLI clears them, no HTTP route clears a flag; irreversible"),
    Tool("agent-registry", "POST", "/agents", "create_agent",
         "BLAST RADIUS: adds one agent record and ledgers registry.registered, no route deletes a record; irreversible"),
    Tool("agent-registry", "PATCH", "/agents/{agent_id}", "update_agent",
         "BLAST RADIUS: renames one agent record and ledgers registry.updated, this tool cannot send status, owner, "
         "domain or manifest_ref; reversible"),
    Tool("agent-registry", "POST", "/agents/{agent_id}/attest", "attest_agent",
         "BLAST RADIUS: overwrites one agent's attested_at and attested_by and so restarts its re-attestation clock, "
         "the earlier values survive only in the ledger; irreversible"),
    Tool("agent-registry", "POST", "/discover", "discover",
         "BLAST RADIUS: scans the supplied text against the registry and returns a report, nothing is stored or ledgered "
         "and the supplied text is sent to the registry; reversible"),
    Tool("federation-broker", "POST", "/crossing", "crossing",
         "BLAST RADIUS: decides one federation crossing and ledgers a federation row with the decision; irreversible"),
    Tool("sealed-ledger", "POST", "/export", "export",
         "BLAST RADIUS: writes an auditor bundle of ledger events into a new directory on the ledger host, no route "
         "deletes it, this tool cannot choose the directory; irreversible"),
)

ALL_TOOLS: tuple[Tool, ...] = TOOLS + WRITE_TOOLS

#: A write tool sends only these body fields (the service model has more; the rest can change authority or state this
#: server must not reach): PATCH carries ``status`` (kill / revive / decommission by another name), ``owner`` and
#: ``manifest_ref`` (can defeat authorized_operators), ``domain`` (steers domain halts): agent_registry/api.py:257-266.
WRITE_BODY_FIELDS = {("agent-registry", "PATCH", "/agents/{agent_id}"): ("name",)}

#: Query parameters a write tool does not offer: ``out_dir`` is a directory on the ledger host (sealed_ledger/api.py:457).
HIDDEN_PARAMS = {("sealed-ledger", "POST", "/export"): frozenset({"out_dir"})}

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

SERVICES = tuple(sorted({t.service for t in ALL_TOOLS} | {k[0] for k in EXCLUDED}))
