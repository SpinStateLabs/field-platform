# STATE — FIELD Platform

> Update before ending any session. Assume many sessions.

## Current phase
Phase 0 (Core) — **complete**. Phase 1 (Spine) — in progress.

## Last completed milestone
- `packages/field-core` v0.1.0 shipped: manifest models (parity with vendored
  `manifest-schema.json` + 4 shipped templates), `field validate` at plugin
  parity, sha-256 hash-chain primitives with first-break reporting, delegation
  token model, conformance verdict model + clause registry, Typer CLI
  (`field validate|templates|verify-chain|version`), 41 tests passing incl.
  adversarial tamper + forged-rehash cases. SPEC/README/demo.sh done.

## Environment facts (verified this machine)
- Python 3.12 NOT installed; available 3.14 (default), 3.11, 3.9.
  Decision: `requires-python >=3.11`, develop on 3.14.2.
- Venv OUTSIDE Google Drive (sync churn): `C:\Users\donal\.venvs\field-platform`.
  Activate: `~/.venvs/field-platform/Scripts/python.exe` (Git Bash) .
- Windows console is cp1252 — CLI forces UTF-8 stdout (see cli.py); write
  files via `--out`, not shell redirect.
- Source templates/schema vendored from local
  `../Force-Field-with-git/Force-Field/plugins/field/skills/field/` (verbatim).

## Next action
1. Build `services/sealed-ledger` (first — delegation-authority depends on it):
   FastAPI append/verify/export + CLI + tamper adversarial test.
2. Then `services/agent-registry` (CRUD + /discover scanner).
3. Then `services/delegation-authority` (mint/revoke/introspect; writes ledger).
4. Phase 1 gate: `docs/capstone-evidence/phase-1.md`, update this file.

## Open questions
- OQ-1: Should service-to-service calls in the local demo authenticate
  (shared-secret header) in v0.1, or is localhost trust acceptable until
  Phase 2? Current plan: localhost trust in v0.1, noted in each LIMITS.
- OQ-2: compliance-crosswalk needs real regulation texts ingested in a later
  session (OSFI E-23, EU AI Act, ISO 42001, NIST AI RMF) — do not fabricate.
- OQ-3: attestation-reporter PDF path on Windows (weasyprint needs GTK) —
  candidate: HTML + headless-Chromium print, decide in Phase 4.

## Phase gate log
- 2026-08-08 — Phase 0 complete: field-core DoD met, 41/41 tests green.
