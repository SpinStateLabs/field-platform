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
  `heartbeat` / `checkin` / `ensure_alive`.
- Hook 1 ACTIONS: pure re-export of `conformance_sentinel.governed`
  (`Governor`, `@governed`, `ActionBlocked`, `ActionEscalated`) — the
  sentinel's own classes; no verdict logic duplicated. Fail closed inherited.
- Hook 2 USAGE: `POST /usage` client, strict (raises on any failure;
  governor's no-cap 404 ⇒ `NoSpendCapError`); `extract_usage()` pulls counts
  from an Anthropic Messages response without importing anthropic.
- Hook 3 LIVENESS: `GET /heartbeat/{agent_id}` (read-only) or, since v1.2,
  `POST /heartbeat/{agent_id}` via `checkin()`, which records `last_seen` so
  the agent stops reading stale on the kill-switch's `GET /liveness`. Same
  fail-closed verdict either way — including on a pre-v1.2 estate, where the
  POST's 404/405 raises `HeartbeatUnreachable` and the SDK halts. `killed=true`, unknown
  agent, non-200, or transport failure all halt (`HeartbeatUnreachable`
  subclasses `AgentKilled`). Opt-in `heartbeat_max_age` re-verifies lazily
  before `check()`.
- Auth: `x-field-auth` merged per request (`_transport.AuthedClient`) so a
  secret exported after construction is honored — matching the server
  middleware, which reads per request.
- `bootstrap.register/mint` (operator-side, not re-exported);
  `fieldagent` CLI: `version | heartbeat | checkin | check | cross | report-usage | mint`
  (check exits 0 ALLOW / 1 BLOCK / 2 ESCALATE; cross exits 0 ALLOW / 1 BLOCK
  or broker unreachable; report-usage exits 3 on rogue findings, mirroring
  `governor usage`).
- v1.2 D5 federation: `FieldAgent.cross` / `FederationClient`
  (`FIELD_FEDERATION_URL`) ASK federation-broker `POST /crossing` and return
  the verdict on an exact ALLOW; anything else raises `CrossingBlocked`
  (`verdict=None` when no decision was obtained — fail closed). Same opt-in
  `heartbeat_max_age` liveness gate as `check()`. It never relays traffic.
- v1.2 X3 canary agent: `field_agent.canary` (an entry point, not
  re-exported by the facade), run as the GB10 compose service
  `canary-agent` (profile `x3`) for `canary-gb10`. `python -m
  field_agent.canary serve` (stdlib `http.server`, no field authn):
  `POST /halt` requires `x-field-kill-origin: kill-switch` (403 otherwise),
  stops the work loop under the same lock the work tick takes, answers 200
  with the nonce parsed from the kill reason `x3-<nonce>` (kill-switch header
  `x-field-kill-reason`, percent-encoded; JSON body `reason` when absent) and
  never exits; `GET /status` `{halted, nonce, since, halts, last_halted_by,
  work_ticks, heartbeat_every, ...}` (latest nonce, first halt time); `GET
  /health`. Optional read-only heartbeat polling
  (`FIELD_CANARY_HEARTBEAT_EVERY`, 0 = off, the default) halts on killed or
  unreachable and never touches the nonce. `python -m field_agent.canary
  x3-check --agent canary-gb10` (inside the kill-switch container) is the X3
  live check: kill `x3-<nonce>` ⇒ `called` + same nonce on `/status`;
  revive ⇒ +1 `kill.revive`; drill on the `canary`-domain record ⇒
  `endpoint_confirmed_ms`; exit 0 all pass / 1 any fail / 2 refused
  (non-canary). Tests: `tests/test_canary_agent.py` (real sockets, a real
  subprocess for never-exits, the real kill-switch app with the real
  `canary-gb10` manifest and `FIELD_KILL_ENDPOINT_ALLOWLIST=canary-agent`).
- Adversarial tests: sentinel-down ⇒ blocked (pins the previously untested
  client-side fail-closed branch of `governed.py`); killed / unknown /
  kill-switch-down ⇒ halt; no-cap usage refused; rogue model + burst
  surfaced with escalation + ledger event; secret-enabled estate: bare
  client 401s where the SDK succeeds.

**Explicit non-goals (v0.1)**
- No background heartbeat thread or process supervision — a thread can set a
  flag, not stop code; halting stays at governed call sites. (The X3 canary's
  optional poller is not the SDK's: its only work loop reads that flag under
  the lock.)
- No async facade, no retry/queueing of usage reports, no best-effort
  metering flag (opt-outs belong visibly at the call site).
- No client-side token validation or scope math — delegation-authority and
  the sentinel own that.
- No new verdict types, clauses, or enforcement semantics of any kind.
