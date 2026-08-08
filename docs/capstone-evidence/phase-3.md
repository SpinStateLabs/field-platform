# Phase 3 evidence — Intelligence (incident-replay · compliance-crosswalk · force-gateway) + integration demo

**Date:** 2026-08-08 · **Status:** COMPLETE · **Tests:** 120 passing
platform-wide (95 through Phase 2, +5 incident-replay, +7 crosswalk,
+13 force-gateway)

## What shipped

**incident-replay** (L · CISO) — deterministic reconstruction of an incident
window: who granted authority (delegation grants overlapping the window),
what ran (ledger timeline with hashes), which clause failed first — rendered
as a RACI-ready markdown post-mortem. The ledger chain is verified before
reporting; a tampered trail brands the whole report INTEGRITY FAILED
(adversarial test edits the trail on disk). No LLM.

**compliance-crosswalk** (law · CCO/GC) — 10 FC-* controls in our own words
mapped to OSFI E-23, EU AI Act, ISO/IEC 42001, NIST AI RMF with **every
citation a `TODO-CITE-AFTER-INGESTION` stub** — an adversarial guard test
fails the build if a real-looking citation appears before the official texts
are ingested. Coverage matrix separates *declared* (manifest, placeholder-
aware) from *evidenced* (live registry/ledger/token/cap artifacts; a broken
chain fails FC-L-01).

**force-gateway** (FORCE · CTO/CDO) — reverse proxy for the Anthropic
Messages API shape injecting FORCE preset blocks composed **verbatim** from
the shipped plugin's protocol.md (analysis F+O+R+C+E · brainstorm F+C+E ·
draft F+C · audit F+R+C+E); caller system prompts preserved; deterministic
regex hygiene telemetry labeled heuristic on every payload; token spend
forwarded to spend-governor; deterministic mock upstream so no demo needs a
key. No secrets in the repo.

**Integration demo** (`integration/demo/run_demo.sh`, verified, ~21 s) —
the capstone scenario end-to-end: validate manifest → register → cap from
manifest → mint → 4 governed drafts (ledger fills, spend metered) → 5th
draft ESCALATE at 96% of cap → rogue `transfer funds` BLOCK `D.scope` →
kill drill 52.84 ms → RACI post-mortem written → 15-event chain verifies
intact. Step 8 (board pack) explicitly deferred to Phase 4's
attestation-reporter. docker-compose provided but flagged UNTESTED (no
docker on the build machine — STATE.md OQ-5).

## Demo output excerpt

```
   INV-004 Dominion Placeholder Co: drafted ($1350.00)
   INV-005 Erewhon Fictional GmbH: ESCALATED to human queue [E.spend_threshold] — not drafted
-- rogue attempt: transfer funds (never granted) --
   BLOCKED [D.scope] as designed
── 6. The 2 a.m. drill ──
   kill confirmed 39.16 ms · heartbeat 41.26 ms · restored=True · total 52.84 ms
── Ledger integrity ──
   15 events, chain intact: True
```

## Enforced vs. declared this phase

Enforced: tamper-branded post-mortems; anti-fabrication citation guard;
verbatim-only FORCE text; system-prompt preservation; deterministic
telemetry. Declared: mapping *correctness* pending regulation ingestion;
model *obedience* to FORCE (measured, not forced); cooperative perimeter.

## Test counts

120 total, all green. New adversarial cases: tampered incident trail;
fabricated-citation guard; flattery detection; unknown-preset rejection.
