# ROADMAP — FIELD Platform

This repo is the reference implementation of the Force Field Protocol. Honesty
line: this file records **what is built**, not a wishlist. Status is verifiable
against `services/` and CI.

## v0 trio — the public "enforcement in v1.1" commitment

Deterministic cores **shipped**; the ADR delta (semantic LLM layers, log-only
mode, measurement harnesses — see `docs/adr/`) is **in progress**, Sentinel first.

| System | FIELD letter · buyer | Deterministic core | ADR delta |
|---|---|---|---|
| Conformance Sentinel | E · CISO | shipped (`services/conformance-sentinel`) | in progress (log-only ✓ · scorecard · semantic judge · self-manifest) |
| FORCE Gateway | FORCE · CTO/CDO | shipped (`services/force-gateway`) | queued (sampled hygiene judge · trend alerts · fail-open+capped) |
| Compliance Crosswalk | law · CCO/GC | shipped (`services/compliance-crosswalk`) | queued (gated suggestions · evidence-pack generator · reg-version staleness) |

## The nine platform systems — SHIPPED

The original brief lists these as *future* roadmap items. In this repo they are
**already built and tested** — the roadmap records that reality.

1. **Agent Registry** — "the passport office": identity, owner, manifest ref; shadow-agent discovery. (I · CIO) — `services/agent-registry` ✓
2. **Delegation Authority Service** — scoped, expiring, revocable tokens chained to a human grantor. (D · GC) — `services/delegation-authority` ✓
3. **Kill-Switch Command Plane** — kill endpoints + heartbeats + timed drills; domain shutdown. (E · CEO/CISO) — `services/kill-switch` ✓
4. **Sealed Ledger Service** — hash-chained append-only record + auditor export; signed anchors. (L · CFO/audit) — `services/sealed-ledger` ✓
5. **Incident Replay Agent** — reconstructs who authorized, what ran, which clause failed → RACI post-mortem. (L · CISO) — `services/incident-replay` ✓
6. **Federation Broker** — inter-org crossing gateway; counterparty manifest validation + Ed25519 signing. (F · CIO/GC) — `services/federation-broker` ✓
7. **Spend & Resource Governor** — token/compute/action metering vs manifest caps; escalate-before-cap; token-cost pricing + rogue detection. (E · CFO/CTO) — `services/spend-governor` ✓
8. **Agent Lifecycle Manager** — expiry, re-attestation, orphan detection vs owner roster. (I/D · CIO/CHRO) — `services/lifecycle-manager` ✓
9. **Executive Attestation Reporter** — board rollup; every number prints its source query. (all · CEO/board) — `services/attestation-reporter` ✓

Plus **ops-console** (`services/ops-console`) — the human dashboard over the fleet.

## Notes

- All figures traceable to live queries or tests; 209 tests, CI green (py 3.11–3.14
  + x86_64 compose), arm64 verified on the GB10.
- **field-agent client SDK** (`packages/field-agent`, 2026-08-29) — the last
  mile: governed actions, strict usage metering, fail-closed heartbeat in a
  few lines; `docs/INTEGRATION.md`.
- The `SpinStateLabs/Force-Field` marketplace ROADMAP can be synced separately if
  these are packaged there as plugins.
