# Phase 0 evidence — Core (field-core)

**Date:** 2026-08-08 · **Status:** COMPLETE · **Tests:** 41 passing

## What shipped

`packages/field-core` v0.1.0 — the single source of truth every service
imports:

- Pydantic v2 models mirroring the FIELD v1 manifest JSON Schema, vendored
  verbatim from the shipped `SpinStateLabs/Force-Field` plugin (schema + all
  four templates: default, financial-agent, read-only-agent,
  client-facing-agent).
- `field validate` at parity with the plugin skill: same status taxonomy
  (VALID / VALID_WITH_WARNINGS / INVALID), same critical-gap rules, same
  warning classes (REPLACE-ME placeholders, absent runtime_protocol,
  past/near-term expiry), same report format.
- sha-256 hash-chain primitives with first-break reporting.
- Delegation token model (revocation beats expiry) and conformance verdict
  model with a stable clause-id registry covering all five letters.
- Typer CLI: `field validate | templates | verify-chain | version`.

## Enforced vs. declared (summary)

Enforced: manifest structure, seal constants ("none" impossible),
non-isolated-requires-peers, chain tamper-evidence, token status semantics.
Declared: ledger durability, non-sha-256 seal algorithms, scope semantics.
Full tables in `packages/field-core/README.md`.

## Test counts

41 tests. Adversarial cases: mid-chain record mutation detected at exact
index; forged re-hash detected at the next link; near-empty manifest yields
a complete gap report (no crash); "none" seal algorithm rejected at both the
model and validator layers.

## Demo output excerpt

```
=== 4. Hash chain: build 5 events, verify, tamper, verify again ===
OK — chain intact over 5 events
TAMPERED — hash mismatch at index 2: stored bf78d60201c8… != recomputed d30a6afc9c27…
(record was mutated)
```

`demo.sh` wall time: ~4 s.

## Notes for evaluators

- Python 3.12 was specified but is not on the build machine; the package
  targets `>=3.11` and is developed on 3.14.2 (uncertainty: LOW — CI on the
  full matrix is future work).
- Windows console encoding (cp1252) required forcing UTF-8 stdout in the
  CLI — recorded in STATE.md as an environment fact.
