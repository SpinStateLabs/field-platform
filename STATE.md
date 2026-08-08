# STATE — FIELD Platform

> Update before ending any session. Assume many sessions.

## Current phase
Phase 2 (Enforcement) — **complete**. Next: Phase 3 (Intelligence).

## Last completed milestone
Phase 2 gate passed (2026-08-08). Enforcement services shipped to DoD:
- **spend-governor** (:8006) — integer-cents metering, caps from manifest
  spend_cap, 80% threshold ESCALATE to human queue before cap BLOCK,
  /caps /spend /status /escalations(+resolve). Demo ~10 s.
- **kill-switch** (:8005) — /kill/{agent}, /kill/domain/{d}, /revive,
  /heartbeat (unknown ⇒ killed=true), /drill with ms report (drill run:
  ~59 ms total). Act-first: kill survives ledger outage. CLI `killswitch`
  (avoids shell builtin). Demo ~11 s.
- **conformance-sentinel** (:8004) — /check → ALLOW/BLOCK/ESCALATE + clause
  id; 8-step sequence (ledger reachability, registry/kill, manifest
  validity via mtime-cached field validate, token introspection, scope
  token∩manifest, irreversible policy, triggers, spend state); all verdicts
  are ledger events; `@governed` decorator + `Governor.check`. Demo boots
  all six services ~21 s.
- field-core: shared HTTP clients at `field_core.clients` (registry get/
  list/set_status, ledger append; lazy httpx); new clause `I.manifest`.
- Platform test total: **95 passing** (41+6+7+8+10+8+15).
- Evidence: docs/capstone-evidence/phase-0.md, phase-1.md, phase-2.md.

## Phase 1 summary (for context)
Spine: sealed-ledger (:8002, hash-chained JSONL, tamper detection),
agent-registry (:8001, SQLite CRUD + /discover shadow-agent scanner),
delegation-authority (:8003, ledger-first fail-closed mint/revoke,
/introspect).

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

## Next action (Phase 3 — Intelligence, suggested order)
1. **incident-replay** (Ledger · CISO): given time window + agent id,
   reconstruct from ledger + registry + delegation who granted authority,
   what ran, which clause failed → RACI-ready post-mortem markdown.
   Deterministic query engine; LLM narration only if clearly labeled.
2. **force-gateway** (FORCE · CTO/CDO): reverse proxy for the Anthropic
   Messages API shape injecting FORCE preset system-prompt blocks
   (analysis/brainstorm/draft/audit — source them from the local
   Force-Field plugin at ../Force-Field-with-git/.../plugins/force/), regex
   hygiene telemetry (labeled heuristic) to a dashboard endpoint. Can also
   report spend to the governor (tokens metering).
3. **compliance-crosswalk** (law · CCO/GC): mapping engine manifest fields →
   framework requirement IDs; v0.1 stub table with TODO citations ONLY
   (OSFI E-23, EU AI Act, ISO 42001, NIST AI RMF) — DO NOT fabricate
   regulation text; ingestion of real texts is a later session.
4. Phase 3 gate: evidence doc, STATE.md, commits.
Also queued: integration/demo (docker-compose + run_demo.sh) — can be built
after Phase 2 since its core scenario (register → mint → act → block →
escalate → kill → drill) is already possible; incident-replay + attestation
complete it.

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
