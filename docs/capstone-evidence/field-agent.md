# Evidence — field-agent client SDK (2026-08-29)

The last mile shipped: `packages/field-agent` puts a real Python agent
under governance in a few lines, and the integration demo's invoicing
agent now runs entirely on it.

## What the committed run log shows

[`field-agent-run.log`](field-agent-run.log) is a real, unedited
`PYTHONUTF8=1 bash integration/demo/run_demo.sh` capture (exit 0):

- **Register → cap → policy → mint** — operator steps, scene 1–2; usage
  policy is new (haiku allow-list, 200k tokens/h).
- **Governed draft loop through the SDK** — 4 drafts, each `check`ed
  (ALLOW), `report_spend`ed ($120) and `report_usage`d (haiku, priced from
  the dated book, `$0.0045`/draft folding into the same $500/day cap).
- **Escalate-before-cap intact** — the 5th draft arrives with the meter at
  96% and is ESCALATED (`E.spend_threshold`), not drafted.
- **Rogue action blocked** — `transfer funds` ⇒ `ActionBlocked [D.scope]`
  before the body ran.
- **Rogue model flagged** — one Opus usage report off the Haiku allow-list
  ⇒ `rogue_model` finding + escalation + `usage.rogue_model` ledger event.
- **Heartbeat halt (scene 6b, new)** — after a real kill, the re-invoked
  agent raises `AgentKilled` at `ensure_alive()` and exits 1 before any
  work; then revived for the post-mortem.
- **Ledger intact** — 23 events, chain verify ok, board pack rendered.

## What the SDK's own suite pins (17 tests, 8 adversarial)

- Sentinel unreachable ⇒ `ActionBlocked` (the client-side fail-closed
  branch of `governed.py`, previously untested anywhere).
- Killed, unknown, and kill-switch-down agents all halt
  (`HeartbeatUnreachable` subclasses `AgentKilled`).
- No-cap usage/spend is refused (`NoSpendCapError`), rogue model/burst
  surface with escalation + ledger event.
- Secret estate: a bare client 401s where every SDK path succeeds
  (per-request `x-field-auth`) — the exact bug the pre-SDK demo agent had.
- Re-export identity: `field_agent.ActionBlocked` IS the sentinel's class.

## Honesty line

The SDK is a client, not an authority — zero new power, refusal is its
only local capability, and an agent that never calls it is not governed
(cooperative perimeter). The Enforced-vs-Declared table in
`packages/field-agent/README.md` is exact.
