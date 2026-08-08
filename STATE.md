# STATE — FIELD Platform

> Update before ending any session. Assume many sessions.

## Current phase
Phase 1 (Spine) — **complete**. Next: Phase 2 (Enforcement).

## Last completed milestone
Phase 1 gate passed (2026-08-08). Spine services shipped to DoD:
- **sealed-ledger** — hash-chained JSONL, /events /verify /export /health,
  tamper + deletion adversarial tests, CLI, demo ~6 s.
- **agent-registry** — SQLite CRUD, /discover scanner (n8n export +
  service-account CSV, labeled heuristic), renamed-workflow adversarial
  test, CLI (scan exits 3 on candidates), demo ~2.5 s.
- **delegation-authority** — SQLite tokens (field-core model), registry
  check on mint (active only), ledger-first mint/revoke fail-closed,
  /introspect fail-closed on unknown ids, expired/revoked adversarial
  tests, CLI, demo boots real spine ~10 s.
- Platform test total: **62 passing** (41 core + 6 + 7 + 8).
- Evidence: docs/capstone-evidence/phase-0.md, phase-1.md.

## Environment facts (verified this machine)
- Python 3.12 NOT installed; available 3.14 (default), 3.11, 3.9.
  Decision: `requires-python >=3.11`, develop on 3.14.2.
- Venv OUTSIDE Google Drive (sync churn): `C:\Users\donal\.venvs\field-platform`.
  Git Bash: `~/.venvs/field-platform/Scripts/python.exe`. Installed editable:
  field-core, sealed-ledger, agent-registry, delegation-authority (+deps
  fastapi/uvicorn/httpx/pytest).
- Windows console is cp1252 — every CLI forces UTF-8 stdout; write files via
  CLI flags (`--out`), not shell redirects.
- SQLite on Windows: brief file-lock lag after killing a serving process
  (delegation demo sleeps 1 s before temp cleanup).
- Source templates/schema vendored verbatim from local
  `../Force-Field-with-git/Force-Field/plugins/field/skills/field/`.

## Next action (Phase 2 — Enforcement, in dependency order)
1. **conformance-sentinel** (`services/conformance-sentinel`, port 8004):
   `/check` (agent id, proposed action, context) → ALLOW/BLOCK/ESCALATE with
   clause id from field-core CLAUSES. Checks: registry status (killed ⇒
   E.kill_switch), token validity via delegation `/introspect` (D.token /
   D.expired / D.revoked), scope allowlist vs. manifest+token (D.scope),
   spend remaining via spend-governor once it exists (E.spend_cap), ledger
   reachability (L.unreachable, fail closed). Blocks/escalates are ledger
   events. Ship the `@governed` decorator here too.
2. **kill-switch** (port 8005): /kill/{agent_id}, /kill/domain/{domain} —
   flips registry status to killed (sentinel then blocks instantly),
   heartbeat endpoint, drill mode with measured ms timing report.
3. **spend-governor** (port 8006): /spend events vs. manifest caps,
   threshold ESCALATE to human queue, hard cap BLOCK; deterministic
   arithmetic only.
4. Phase 2 gate: evidence doc, STATE.md, commits.

## Open questions
- OQ-1: inter-service authn deferred — localhost trust in v0.1, stated in
  every LIMITS. Revisit before any non-local deployment.
- OQ-2: compliance-crosswalk must ingest real regulation texts in a later
  session (OSFI E-23, EU AI Act, ISO 42001, NIST AI RMF) — never fabricate.
- OQ-3: attestation-reporter PDF path on Windows — candidate: HTML +
  headless-Chromium print. Decide in Phase 4.
- OQ-4: sentinel needs the agent's manifest at check time. Plan: registry
  `manifest_ref` points to a YAML the sentinel loads+validates (field-core),
  cached with mtime invalidation. Confirm in Phase 2 build.

## Phase gate log
- 2026-08-08 — Phase 0 complete: field-core DoD met, 41/41 tests green.
- 2026-08-08 — Phase 1 complete: spine DoD met, 62/62 platform tests green.
