# Phase 4 evidence — Edge & Executive (federation-broker · lifecycle-manager · attestation-reporter)

**Date:** 2026-08-08 · **Status:** COMPLETE — **all 12 systems shipped** ·
**Tests:** 139 passing platform-wide (120 through Phase 3, +7
federation-broker, +6 lifecycle-manager, +6 attestation-reporter)

## What shipped

**federation-broker** (F · CIO/GC) — inter-org crossing gateway. Six-step
decision: counterparty manifest VALID → not isolated → names us as a peer →
active GC-registered contract → scope in contract → data class in contract.
Every crossing is a ledger event. The two-org demo shows an in-contract
ALLOW and a customer-PII over-reach BLOCK. Top LIMIT stated plainly:
manifests are unsigned in v0.1, so the contract allowlists — our record,
not the counterparty's claim — are the real gate.

**lifecycle-manager** (I/D · CIO/CHRO) — a scheduled CLI job (exit 3 on
findings) sweeping registry + delegation for expiring authorities (30 d
horizon), re-attestation due (90 d), and orphans vs. an `owners.csv` roster.
Every finding is a ledger escalation. Auto-kill exists **only** behind
`--auto-kill-orphans` — an adversarial test proves the flag-off sweep never
kills; kills route through kill-switch and are idempotent across re-sweeps.

**attestation-reporter** (all · CEO/board) — `attest render` produces the
board pack (JSON + HTML + PDF) from live services. **No number without a
source**: the `Metric` model cannot be constructed with a value and no
literal source query, and an unreachable service renders as `unavailable`,
never a fabricated zero (adversarial test). Ledger integrity leads the pack;
a tampered chain surfaces as BROKEN. PDF via headless Edge **verified
working on this machine** — OQ-3 resolved as best-effort-with-fallback.

**Integration demo completed** — `run_demo.sh` now executes all 8 steps of
the capstone scenario (~23 s), ending with the board pack whose every
figure prints its query.

## A found-and-fixed defect, on the record

Demo review caught the reporter's "Tokens revoked" metric reading 1 when
nothing had been revoked: the fetch helper collapsed the token list to its
length before the transform ran. Fixed (transforms now receive the raw
payload); the test now stages a revoked token and pins all three token
metrics. Recorded here because a governance product that miscounts its own
evidence has no business reporting anyone else's.

## Demo output excerpt (run_demo.sh step 8)

```
   Ledger chain integrity                     INTACT       <- GET http://127.0.0.1:8002/verify
   Agents in production (active)              1 agents     <- GET http://127.0.0.1:8001/agents?status=active
   Conformance rate (ALLOW / all verdicts)    71.4 %       <- GET http://127.0.0.1:8002/events?event_type=conformance.allo…
   Kill drills completed                      1 events     <- GET http://127.0.0.1:8002/events?event_type=kill.drill.compl…
```

## Platform totals at the 12-system mark

139 tests · 12 systems + field-core, each with SPEC.md, typed API/CLI,
adversarial test, <60 s demo, Enforced-vs-Declared README · 16 conventional
commits · every phase gate recorded in STATE.md.

## Carried forward (deliberately)

- OQ-1 localhost trust (stated in every LIMITS) — authn before any
  non-local deployment.
- OQ-2 regulation-text ingestion for crosswalk citations.
- OQ-5 docker-compose verification on a docker-equipped machine.
- Manifest signing for federation (top LIMIT of the F letter).
