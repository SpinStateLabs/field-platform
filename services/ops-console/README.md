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
| Mode badge | `LIVE` (server push) or `POLL 5s` (fallback) | — |
| Agents | id, owner, domain, status; select boxes | kill · drill · revive (no revive for `retired` — a decommission is not undone from here) · bulk kill/drill/revive of the selection · **FLEET HALT** |
| Agent drawer (click an id) | registry record, heartbeat, tokens, usage, last 50 ledger events; **view manifest** (raw YAML + validation badge) | kill · drill · revive |
| Tokens | scope, expiry, state | revoke (active only) |
| Spend escalations | the human queue | resolve (name recorded) |
| Harness | dry-run form: agent + token + action (selection survives refreshes) | ask the sentinel → real verdict, really ledgered |
| Ledger | live tail (last 25) or a filtered query: agent, event type, since/until, limit; click a row for its payload | load older · export CSV / JSON |
| Platform services | health of all 12 services; lifecycle findings, attestation signing, crosswalk staleness, federation contracts | link to the board pack |

Live push: `GET /api/stream` (server-sent events). The page reads it with
`fetch()` so the shared-secret header goes with it, and falls back to a 5 s
poll when the stream is refused or drops. Single self-contained HTML file — no npm, no
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
| A decommissioned (`retired`) agent offers no `revive` button | **Enforced in code** | the agents table branches on `retired` before the revive branch (test reads the served page), and the kill-switch answers **409** to `/revive` for a retired agent even from a stale tab (test) |
| Bulk ops and FLEET HALT add no power | **Enforced in code** | bulk = one kill-switch call per agent (each ledgered, a refusal recorded per agent, the rest continue); halt = the kill-switch's own `POST /kill/domain/{d}` per domain; tests assert per-agent `kill.agent` events with the operator |
| FLEET HALT needs a typed confirmation | **Enforced in code** | 422 unless `confirm` is exactly `HALT`, plus a mandatory operator and reason (test); the page also disables the button until then |
| The manifest viewer cannot read outside `FIELD_MANIFEST_DIR` | **Enforced in code** | real path (symlinks followed) must be inside the dir, suffix `.yaml/.yml/.json`, ≤256 KB, else 403; unset dir = refused, never "relative to CWD". Tests: `../` traversal, absolute paths, symlink escape, `.pem`, oversize; no secret text in any response |
| The live stream is behind the shared secret | **Enforced in code** | `/api/stream` is not an open path (401 test); stream count capped (`FIELD_CONSOLE_MAX_STREAMS`, default 8, 503 beyond) |
| Ledger exports are evidence | **Declared only — and NOT claimed** | `/api/events/export` is an unsigned copy of what the screen shows; a filtered subset does not verify as a chain alone. Evidence bundles come from the ledger's `POST /export` |
| The operator *is* who they typed | **Declared only** | names are recorded, not authenticated — per-caller identity is the known platform gap |
| The console shows *everything* | **Declared only** | it shows what the services know; ungoverned processes appear only via discovery |

## LIMITS

- Push to the browser, poll upstream: no service publishes changes, so each
  stream rebuilds the overview every 2 s server-side and pushes only
  changes. A kill issued elsewhere shows up within ~2 s (stream) or 5 s (poll).
- The stream cap is soft (a burst of simultaneous opens can pass it by a few).
- Ledger paging: the ledger has no offset cursor, so "load older" re-queries
  with `until=<oldest shown>` and drops duplicates.
- FLEET HALT halts the domains of the agents the registry listed at that
  moment; an agent registered mid-halt in a new domain is not covered.
- Operator attribution is honest-recording, not authentication (same
  shared-secret trust domain as everything else).
- The harness writes real `conformance.*` events — that is a feature
  (dry-runs are auditable), but know your test checks appear in the ledger
  tail and the board pack's verdict counts.
- Built for demo/pilot fleet sizes (bulk caps at 100 agents per request).
- The board-pack link opens `/attest/pack.html` directly; on a locked estate
  the browser cannot attach `x-field-auth` to a plain link, so it answers 401.
