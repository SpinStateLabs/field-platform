# SPEC — lifecycle-manager

**Purpose:** Scheduled sweep over agent-registry + delegation-authority:
report authorities expiring within a horizon, agents due for
re-attestation, and orphaned agents whose owner is absent from the human
roster (owners.csv). Every finding is a ledger escalation; orphan auto-kill
exists but only behind an explicit flag.

**Exec owners:** CIO / CHRO.

**FIELD letters:** I (identity/ownership) + D (delegation hygiene).

**v0.1 scope**
- `lifecycle sweep` CLI (exit 3 on findings) with `--roster`,
  `--expiry-days` (30), `--reattest-days` (90), `--auto-kill-orphans`
  (default OFF), `--operator`, `--markdown`.
- Deterministic engine: token expiry window, `updated_at` staleness,
  case-insensitive roster membership.
- Ledger events: `lifecycle.expiring_authority | reattestation_due | orphan`;
  auto-kills go through kill-switch with a sweep-attributed reason.
- Idempotent: re-sweeps re-report, never double-kill.
- Adversarial test: auto-kill without the flag must not happen.

**Explicit non-goals (v0.1)**
- No scheduler (Task Scheduler/cron owns cadence).
- No identity resolution on owners (exact-string roster match).
- No HTTP API — CLI job only.
- No re-attestation workflow (reporting only; `attested_at` is future work).
