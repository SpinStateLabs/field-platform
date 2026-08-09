# ops-console

The human's dashboard over every governed agent: watch, kill, revive,
drill, revoke, resolve — and dry-run any proposed action against the
sentinel before an agent tries it. Port **:8011**. Exec owners: **everyone
with a switch** (CISO for kills, CFO for spend, GC for tokens).

## Design rule: a client, not an authority

The console adds **zero new power**. Every button proxies the service that
owns the action — kill-switch, delegation-authority, spend-governor,
conformance-sentinel — so every action is authenticated, attributed
(operator name is mandatory), and lands on the sealed ledger exactly as if
a CLI operator had done it. Delete the console and nothing about the
governance model changes; it only makes existing power visible.

## What's on the screen

| Panel | Shows | Actions |
|---|---|---|
| Ledger badge | chain INTACT/BROKEN, live | — |
| Agents | id, owner, domain, status | kill · drill · revive |
| Tokens | scope, expiry, state | revoke (active only) |
| Spend escalations | the human queue | resolve (name recorded) |
| Harness | dry-run form: agent + token + action | ask the sentinel → real verdict, really ledgered |
| Ledger tail | last 25 events, clause-colored | — |

Auto-refreshes every 5 s. Single self-contained HTML file — no npm, no
build step, works from `file://`-hostile corporate laptops because it's
just the one page served by the console itself.

## Run

```
console serve [--port 8011]     # FIELD_*_URL env vars point at the services
```

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Mutations go through the owning service (and its ledger writes) | **Enforced in code** | pure proxy; tests assert registry flip + `kill.agent` event with the console operator's name |
| Operator name is mandatory on every mutation | **Enforced in code** | 422 on empty operator |
| Unreachable services shown as unavailable, never as empty state | **Enforced in code** | attestation-reporter rule, tested |
| Upstream refusals surface verbatim | **Enforced in code** | 404/409/502 pass through |
| With `FIELD_SHARED_SECRET` set: shell page open, all `/api/*` locked | **Enforced in code** | authn split test; browser prompts for the secret (kept in sessionStorage) |
| The operator *is* who they typed | **Declared only** | names are recorded, not authenticated — per-caller identity is the known platform gap |
| The console shows *everything* | **Declared only** | it shows what the services know; ungoverned processes appear only via discovery |

## LIMITS

- Poll-based (5 s), not push — a kill issued elsewhere shows up on the next
  refresh.
- Operator attribution is honest-recording, not authentication (same
  shared-secret trust domain as everything else).
- The harness writes real `conformance.*` events — that is a feature
  (dry-runs are auditable), but know your test checks appear in the ledger
  tail and the board pack's verdict counts.
- No pagination; built for demo/pilot fleet sizes.
