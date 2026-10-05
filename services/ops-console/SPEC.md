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
- No websockets; no charts (attestation-reporter
  owns board-grade reporting).

**v1.2 additions (B4)**
- The agents table hides `revive` for `retired` agents (decommissioned;
  the kill-switch answers 409 to a revive attempt regardless). UI half
  only — the enforceable guard lives in kill-switch.

**v0.2 additions (operator feature pack, 2026-10-04)**
- Harness selections survive the refresh (`fillSelect`: keep value, skip
  while focused, skip when options unchanged).
- Drill to details: `GET /api/agents/{id}` (record, heartbeat, tokens, usage,
  last 50 events); `GET /api/agents/{id}/manifest` (read-only, path-guarded
  to `FIELD_MANIFEST_DIR`, validation via field-core `ManifestResolver`).
- Platform panel: `GET /api/platform` (12 health checks in parallel,
  lifecycle `/findings`, federation `/contracts`, crosswalk `/staleness`,
  attest signing state).
- Ledger: `GET /api/events` (agent/type/since/until/limit) and
  `GET /api/events/export?format=csv|json` (unsigned convenience copy).
- Bulk: `POST /api/agents/bulk` (kill|drill|revive, ≤100 ids, per-agent
  results); `POST /api/fleet/halt` (typed `HALT`, kill-switch domain halt).
- Live push: `GET /api/stream` (SSE via fetch, change-only frames,
  keep-alives, capped); polling remains the fallback.
- Still no new authority, storage or ledger writes of its own.
