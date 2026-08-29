# SPEC — field-agent

**Purpose:** The last mile. A real Python agent puts itself under governance
in ~5 lines: every tool call checked by the conformance-sentinel before it
runs, every LLM call metered into the spend-governor, liveness polled from
the kill-switch with a fail-closed halt. The SDK is a client, not an
authority — it adds zero new power; its only local capability is refusal.
An agent that never calls it is not governed (cooperative perimeter).

**Exec owner:** CTO (the client edge of every letter).

**FIELD letter:** All five (client edge); primarily E — Enforcement.

**v0.1 scope**
- `FieldAgent(agent_id, token_id, *, …_client/…_url seams, heartbeat_max_age)`
  facade: `check` / `governed` / `report_usage` / `report_usage_from` /
  `heartbeat` / `ensure_alive`.
- Hook 1 ACTIONS: pure re-export of `conformance_sentinel.governed`
  (`Governor`, `@governed`, `ActionBlocked`, `ActionEscalated`) — the
  sentinel's own classes; no verdict logic duplicated. Fail closed inherited.
- Hook 2 USAGE: `POST /usage` client, strict (raises on any failure;
  governor's no-cap 404 ⇒ `NoSpendCapError`); `extract_usage()` pulls counts
  from an Anthropic Messages response without importing anthropic.
- Hook 3 LIVENESS: `GET /heartbeat/{agent_id}`; `killed=true`, unknown
  agent, non-200, or transport failure all halt (`HeartbeatUnreachable`
  subclasses `AgentKilled`). Opt-in `heartbeat_max_age` re-verifies lazily
  before `check()`.
- Auth: `x-field-auth` merged per request (`_transport.AuthedClient`) so a
  secret exported after construction is honored — matching the server
  middleware, which reads per request.
- `bootstrap.register/mint` (operator-side, not re-exported);
  `fieldagent` CLI: `version | heartbeat | check | report-usage | mint`
  (check exits 0 ALLOW / 1 BLOCK / 2 ESCALATE; report-usage exits 3 on
  rogue findings, mirroring `governor usage`).
- Adversarial tests: sentinel-down ⇒ blocked (pins the previously untested
  client-side fail-closed branch of `governed.py`); killed / unknown /
  kill-switch-down ⇒ halt; no-cap usage refused; rogue model + burst
  surfaced with escalation + ledger event; secret-enabled estate: bare
  client 401s where the SDK succeeds.

**Explicit non-goals (v0.1)**
- No background heartbeat thread or process supervision — a thread can set a
  flag, not stop code; halting stays at governed call sites.
- No async facade, no retry/queueing of usage reports, no best-effort
  metering flag (opt-outs belong visibly at the call site).
- No client-side token validation or scope math — delegation-authority and
  the sentinel own that.
- No new verdict types, clauses, or enforcement semantics of any kind.
