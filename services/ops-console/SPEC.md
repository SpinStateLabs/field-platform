# SPEC — ops-console

**Purpose:** Single-pane dashboard for humans harnessing governed agents:
live fleet state (agents, tokens, escalations, ledger tail + integrity)
and the existing control actions (kill/revive/drill, revoke, resolve,
sentinel dry-run) — all proxied through the owning services so the console
holds no authority of its own.

**Exec owners:** cross-cutting (CISO kills, CFO spend queue, GC tokens).

**v0.1 scope**
- FastAPI :8011 — `GET /` (self-contained HTML, no build tooling),
  `GET /api/overview` (aggregation with unavailable-not-faked sections),
  action proxies: kill/revive/drill, token revoke, escalation resolve,
  sentinel `/api/check` dry-run harness.
- Operator name mandatory on mutations (recorded upstream on the ledger).
- Authn split: `/` and `/health` open; `/api/*` requires `x-field-auth`
  when `FIELD_SHARED_SECRET` is set (page prompts, sessionStorage).
- 5 s polling refresh; clause-colored ledger tail.
- CLI: `console serve`.

**Explicit non-goals (v0.1)**
- No new authority, storage, or ledger writes of its own.
- No user accounts/RBAC (shared-secret trust domain; identity is the
  platform-wide gap).
- No websockets/streaming; no pagination; no charts (attestation-reporter
  owns board-grade reporting).
