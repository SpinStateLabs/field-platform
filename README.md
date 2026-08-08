# FIELD Platform

Reference implementations of 12 enterprise AI-governance systems grounded in
the **Force Field Protocol**: **FORCE** (runtime prompt protocol — Forbid
flattery · Oppose premise · Reference sources · Chain-of-thought · Express
uncertainty) and **FIELD** (design-time governance — Federation · Identity ·
Enforcement · Ledger · Delegation).

Built by Spin State Labs (Waterloo, ON). Humans organize; AI operates.
Simultaneously Spin State's product line and the University of Waterloo
AI-CTO capstone initiative.

## The honesty line

FIELD v1.0 (the shipped Claude Code plugin) **declares** governance in a
manifest. This platform is what makes it **enforced**. Every service README
carries an *Enforced vs. Declared* table stating exactly which guarantees are
enforced in code and which are declarations awaiting infrastructure. A
governance product that overclaims has already failed.

## Layout

```
field-platform/
  STATE.md                  # current phase, last milestone, next action — read this first
  packages/field-core/      # single source of truth for all schemas
  services/<system>/        # one directory per governance system (12 total)
  integration/demo/         # docker-compose end-to-end scenario (capstone centerpiece)
  docs/capstone-evidence/   # phase-gate evidence artifacts
```

## The 12 systems

| # | System | FIELD letter | Exec owner | Phase |
|---|--------|--------------|-----------|-------|
| 1 | agent-registry | Identity | CIO | 1 |
| 2 | sealed-ledger | Ledger | CFO/audit | 1 |
| 3 | delegation-authority | Delegation | GC | 1 |
| 4 | conformance-sentinel | Enforcement | CISO | 2 |
| 5 | kill-switch | Enforcement | CEO/CISO | 2 |
| 6 | spend-governor | Enforcement | CFO/CTO | 2 |
| 7 | incident-replay | Ledger | CISO | 3 |
| 8 | compliance-crosswalk | (law) | CCO/GC | 3 |
| 9 | force-gateway | FORCE | CTO/CDO | 3 |
| 10 | federation-broker | Federation | CIO/GC | 4 |
| 11 | lifecycle-manager | Identity/Delegation | CIO/CHRO | 4 |
| 12 | attestation-reporter | all | CEO/board | 4 |

Phase 0 is `packages/field-core` — models, validation, hash-chain primitives.

## Development

Python ≥3.11 (developed on 3.14). The venv lives **outside** Google Drive to
avoid sync churn: `C:\Users\donal\.venvs\field-platform`.

```
pip install -e packages/field-core[dev]
pytest packages/field-core
```

Each system meets the same Definition of Done: `SPEC.md`, Pydantic-typed API,
CLI verbs, pytest suite with at least one adversarial case, `demo.sh` (<60s),
README with Enforced-vs-Declared table and LIMITS section.

## Naming

"Force Field Protocol" is the umbrella. "The F.O.R.C.E. Framework" and
"The F.I.E.L.D. Framework" name the acronym structures. It is never
"Force Field Framework."
