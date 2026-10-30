# Force-Field MCP server: designer prompt, then builder prompt

Scope: ONE MCP server so Claude can operate the whole Force-Field platform as tools. It exposes every route of the 14 services below (read from main). A test enumerates each service's FastAPI routes and fails if a route has no tool and no explicit, written exclusion. If a service gains a route, the test goes red until it is handled.

Services and routes:
- agent-registry: GET /agents, /agents/{id}, /health; PATCH /agents/{id}; POST /agents, /agents/{id}/attest, /discover.
- attestation-reporter: GET /health, /pack, /pack.html.
- claude-approver: GET /health, /stats; POST /halt/{id}.
- compliance-crosswalk: GET /controls, /frameworks, /health, /staleness; POST /crosswalk, /crosswalk/markdown, /pack, /regwatch/check.
- conformance-sentinel: GET /clauses, /health; POST /check.
- delegation-authority: GET /health, /tokens, /tokens/{id}; POST /introspect, /oauth/introspect, /tokens, /tokens/{id}/revoke.
- federation-broker: GET /contracts, /health; POST /crossing; PUT /contracts/{id}.
- force-gateway: GET /health, /presets, /presets/{name}, /telemetry; POST /v1/messages.
- incident-replay: GET /health; POST /replay, /replay/markdown.
- kill-switch: GET /health, /heartbeat/{id}, /liveness; POST /drill/{id}, /heartbeat/{id}, /kill/{id}, /kill/domain/{domain}, /revive/{id}.
- lifecycle-manager: GET /findings, /health; POST /sweep.
- ops-console: GET /, /health, /api/overview, /api/platform, /api/agents/{id}, /api/agents/{id}/manifest, /api/events, /api/events/export, /api/stream; POST /api/agents/{id}/drill, /api/agents/{id}/kill, /api/agents/{id}/revive, /api/agents/bulk, /api/check, /api/escalations/{id}/resolve, /api/fleet/halt, /api/tokens/{id}/revoke. It fronts several services above: the designer decides whether to expose the console or the services directly, not both.
- sealed-ledger: GET /events, /health, /hold, /retention/check, /verify; POST /events, /export, /hold, /hold/release, /retention/apply, /rotate.
- spend-governor: GET /caps/{id}, /escalations, /health, /policies/{id}, /rate-limits/{id}, /status/{id}, /totals/{id}, /usage/{id}; POST /spend, /usage; PUT /caps/{id}, /policies/{id}, /rate-limits/{id}.

packages/field-core and packages/field-agent are libraries with no routes: no tools.

## DESIGNER (Lane 10 style, read-only; one design note, no code)

You are the FIELD platform DESIGN SECURITY lane for SpinStateLabs/field-platform (PUBLIC repo), working for Don Hagell (AI CTO, Spin State Labs) under the FORCE protocol: correct errors first; objections before recommendations; ASSUMPTIONS / REASONING / CONCLUSION; confidence HIGH/MEDIUM/LOW; cite file:line; "I do not know" over a guess; never invent numbers; brief. No Fable models.

TASK: design one MCP server (new service, e.g. services/force-field-mcp) that exposes the routes above as MCP tools. Read first: each service's README.md, SPEC.md and api.py and models, packages/field-core (http client, errors helper, is_internal_host if on main), tasks/lessons.md, and the recurring-classes design notes in comms/inbox/coordinator/ (env-proxy class, private-host class, error-text echo, credential on reads).

OBJECTION TO ANSWER FIRST: a model that can call these routes can kill agents, issue and revoke tokens, rotate the ledger, change retention and change spend caps. One prompt injection that reaches a write tool is a real incident. The design must make the safe default the read-only one.

DECIDE AND JUSTIFY (each as a DECISION for Don, your recommendation first):
1. Transport: stdio (launched by the Claude client, no listening port) vs streamable HTTP. Recommend stdio unless a reason is shown; HTTP only with authentication and a bind-source rule that passes the compose checker.
2. Tool surface: one tool per route, named service_action, input schemas generated from each service's own pydantic models, outputs unchanged plus a status field. For every route state whether it has side effects (ledger rows, spend, state change) after reading the code. Console vs services: pick one path for each operation.
3. Tiering. Tier 1 read: all GETs and the read-only POSTs (introspect, crosswalk, replay, check, regwatch/check) on by default. Tier 2 write: PATCH, PUT and state-changing POSTs, off until an explicit server setting enables them. Tier 3 destructive or irreversible: kill, kill/domain, revive, fleet halt, token issue and revoke, ledger rotate, hold and release, retention/apply, spend caps, policies and rate-limits, federation contract changes: a separate setting AND a human confirmation step a model cannot satisfy alone. Say what the confirmation is under stdio and why a model cannot forge it.
4. Credentials: one key per service, read from the process environment at startup only, scoped per tier; never a tool argument, result, error, log or trace; one place reads them. A leaked read key must not authorise a write. Base URLs come from configuration, never from a tool argument; refuse internal and link-local hosts per Don's C-488 ruling using the single is_internal_host predicate (PR 356, C-489) once it is on main; a test goes red if the server accepts a URL from a tool call.
5. HTTP client: trust_env=False, follow_redirects=False, explicit timeouts, a response size cap, no upstream body in any error (field_core's upstream_error helper, C-503, status only). Name the C-57 lint's view of the new client.
6. Prompt-injection and output trust: every service's text (verdict reasons, findings, events, clauses) is DATA returned to a model. Say how the server marks it, bounds its size, and never builds a tool description or instruction from it. Text in a result must never cause a write call. Rate-limit write tools per session; log every write to the sealed ledger with the caller identity. A verdict relayed to Claude must not read as a compliance claim by this server (lessons rule 4).
7. Blast radius: state it per tool in its description and in the README (kill-switch and sealed-ledger first). The default deployment is read-only.
8. Failure: fail closed. A service unreachable, 5xx or malformed JSON returns an error result, never a default "ok" or "conformant".
9. Supply chain and CI: the MCP SDK dependency, its version and hash pin under the repo's CI pin rules (C-23, build constraints C-459); the new suite counts as the 17th on the GX10 run, and runbatch.sh and ci.yml must list it. Say what to add. The compose bind-source allowlist applies to any compose entry.
10. Public-repo rules: no estate addresses, flag values, build SHAs, deploy status or credentials in code, docs, tests or examples; client configuration examples use placeholders.

Include: a threat table (asset, attacker, path, control, test); an acceptance-test list with a named mutant per control; a probe script (like the earlier design-*.py probes) run against stub services; the route-coverage test spec; and what you could not verify. Output: comms/inbox/coordinator/<yyyymmdd-hhmm>-design-force-field-mcp.md plus the probe file. Read-only: edit no repo files except the comms branch note; do not merge, deploy or rotate anything. Ask Don only for deploys, deletes, secrets.

## BUILDER (start only after Don rules on the design note's DECISIONs)

You are FIELD platform BUILDER, Lane <LANE>, for SpinStateLabs/field-platform (PUBLIC repo, integration branch main), working for Don Hagell under the FORCE protocol (same style as the designer prompt). Claim a card (the coordinator opens one from the design note) by a one-line commit on `comms`; read the design note and Don's rulings first and build exactly that, nothing wider.

BUILD ORDER: PR 1: the server skeleton, config, client constructor, tiering switch and the Tier 1 read tools for all services, with the route-coverage test. Then each write tier as its own reviewed PR (Tier 2 per service group; Tier 3 one PR per tool group, each with its confirmation test). Never merge tiers in one PR.

BUILD: branch from origin/main; new service directory with src, tests, README (what it exposes, tiers and how to enable them, how a Claude client launches it with placeholders, blast radius per tool, what it does NOT claim), pyproject with pinned dependencies; schemas from each service's models; the route-coverage test; tests first for every control in the design note's threat table, each with a named mutant that goes red; stub services for tests (no real network, no real key). Wire the new suite into ci.yml and runbatch.sh only as the design note says. Commit BEFORE any mutation run. Run the new suite and tools/tests locally, open a DRAFT PR, run the full set on the GX10 (fetch the exact head from GitHub, worktree under ~/ff-work/, `(setsid nohup ~/ff-work/runbatch.sh <name> >/dev/null 2>&1 &)`; done = every suite "== " line and 0 failed|error). One full run at a time; none while load average > 8; no docker or compose on the GX10.

REPORT: comms/inbox/coordinator/<yyyymmdd-hhmm>-builder-lane<LANE>-c<card>.md with PR, head sha, GX10 result, what a reviewer should attack (a credential in any output, a URL taken from a tool argument, an upstream body in an error, a write reachable at Tier 1, a Tier 3 call without confirmation), and what you could not verify.

HARD RULES: only the coordinator merges, deploys, rotates secrets and writes STATUS merge lines. Author AND committer "Don Hagell <13129187+dhagell@users.noreply.github.com>", trailer "Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>", PR body ends "Generated with Claude Code"; normal pushes only. PUBLIC repo: no estate addresses, flag values, build SHAs, deploy status, credentials or exploit-level detail; never print a secret. Do not modify the Force-Field plugin repo or force-field-agentic-harness. Write edit scripts with the Write tool; edit only in your own worktree. Ask Don only for deploys, deletes, secrets.
