# STATE — FIELD Platform

> Update before ending any session. Assume many sessions.

## Current phase
Phase 3 (Intelligence) — **complete**, including the integration demo.
Next: Phase 4 (Edge & Executive: federation-broker, lifecycle-manager,
attestation-reporter).

## Last completed milestone
Phase 3 gate passed (2026-08-08). Shipped to DoD:
- **incident-replay** (:8007) — deterministic post-mortems (who granted
  authority / what ran / which clause failed), ledger-verify gate brands
  tampered trails INTEGRITY FAILED, RACI table, markdown output. 5 tests.
- **compliance-crosswalk** (:8008) — 10 FC-* controls, ALL citations
  TODO-CITE-AFTER-INGESTION (guard test enforces; never fabricate),
  declared-vs-evidenced coverage matrix with live evidence collector. 7 tests.
- **force-gateway** (:8009) — Anthropic-shape proxy, FORCE presets composed
  verbatim from vendored plugin protocol.md, system-prompt-preserving
  injection, labeled regex telemetry, governor token spend, deterministic
  mock upstream (no keys needed). 13 tests.
- **integration demo** — run_demo.sh VERIFIED (~21 s, local processes):
  validate → register → cap-from-manifest → mint → 4 drafts allowed +
  metered → 5th ESCALATE E.spend_threshold → transfer-funds BLOCK D.scope →
  kill drill 52.84 ms → post-mortem → 15-event chain intact.
  docker-compose.yml + Dockerfile written but UNTESTED (no docker here).
- Platform test total: **120 passing**.
- Evidence: docs/capstone-evidence/phase-0..3.md.

Phase 2 summary (context): spend-governor (:8006, integer-cents metering,
escalate-before-cap), kill-switch (:8005, act-first halt + drills),
conformance-sentinel (:8004, 8-step /check + @governed decorator).
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

## Next action (Phase 4 — Edge & Executive, suggested order)
1. **federation-broker** (F · CIO/GC, :8010): validate a counterparty's
   manifest against a `federation_contract` (allowed scopes, data classes);
   ALLOW/BLOCK crossing events to ledger; v0.1 = two local "orgs"
   exchanging one governed request (local processes fine; compose optional).
2. **lifecycle-manager** (I/D · CIO/CHRO, :8011 or CLI-only job):
   expiring-authorities report, re-attestation due list, orphan detection
   vs. an owners.csv roster → auto-ESCALATE + optional auto-kill flag
   (off by default).
3. **attestation-reporter** (all · CEO/board, :8012 or CLI): render the
   quarterly board pack from live services — agents in production,
   conformance %, blocks/escalations, incidents, expiring authorities —
   HTML (+ PDF via headless Chromium if available, else HTML only —
   resolve OQ-3). EVERY number must print its source query. Completes
   run_demo.sh step 8.
4. Phase 4 gate: evidence doc, STATE.md, commits. Then: regulation-text
   ingestion session for crosswalk citations (OQ-2); docker-compose
   verification on a docker-equipped machine (OQ-5).

## Open questions
- OQ-1: inter-service authn deferred — localhost trust in v0.1, stated in
  every LIMITS. Revisit before any non-local deployment.
- OQ-2: compliance-crosswalk must ingest real regulation texts in a later
  session (OSFI E-23, EU AI Act, ISO 42001, NIST AI RMF) — never fabricate.
- OQ-3: attestation-reporter PDF path on Windows — candidate: HTML +
  headless-Chromium print. Decide in Phase 4.
- OQ-4: RESOLVED in Phase 2 — sentinel resolves registry `manifest_ref`
  with mtime-cached field-core validation; invalid ⇒ I.manifest BLOCK.
- OQ-5: docker not installed on this machine; integration compose files
  are written but UNTESTED — verify on a docker-equipped machine or CI.
  run_demo.sh (local processes) is the verified demo path.

## Phase gate log
- 2026-08-08 — Phase 0 complete: field-core DoD met, 41/41 tests green.
- 2026-08-08 — Phase 1 complete: spine DoD met, 62/62 platform tests green.
- 2026-08-08 — Phase 2 complete: enforcement DoD met, 95/95 tests green.
- 2026-08-08 — Phase 3 complete: intelligence + integration demo, 120/120
  tests green; run_demo.sh verified ~21 s.
