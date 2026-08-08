# Phase 1 evidence — Spine (agent-registry · sealed-ledger · delegation-authority)

**Date:** 2026-08-08 · **Status:** COMPLETE · **Tests:** 62 passing platform-wide
(41 field-core + 6 sealed-ledger + 7 agent-registry + 8 delegation-authority)

## What shipped

**sealed-ledger** (L · CFO/audit) — append-only JSONL event API; every event
sha-256-chained; `/verify` walks the chain and reports the first break;
auditor export = JSONL copy + verification summary. CLI:
`ledger append|verify|export|serve`.

**agent-registry** (I · CIO) — CRUD for agent records (slug id, human owner,
domain, manifest ref, active/killed/retired). Shadow-agent discovery v0.1:
deterministic scanner over an n8n workflow export + a service-account CSV,
emitting "unregistered agent candidates" (labeled heuristic, no LLM). CLI:
`registry add|list|scan|serve`.

**delegation-authority** (D · GC) — scoped, expiring, revocable tokens bound
to a registered **active** agent + a human grantor. `/tokens`,
`/tokens/{id}/revoke` (idempotent), `/introspect`. Mint/revoke are
ledger-first and fail closed when the ledger is unreachable. CLI:
`delegation mint|revoke|introspect|list|serve`.

## Enforced vs. declared (what an evaluator should check)

| Claim | Where proven |
|---|---|
| Mid-chain mutation detected at exact index | `sealed-ledger/tests` adversarial case (on-disk edit) |
| Record deletion detected | `sealed-ledger/tests` |
| Renamed AI workflow still surfaces in discovery | `agent-registry/tests` adversarial case (keys on node types) |
| Expired token fails introspection | `delegation-authority/tests` |
| Revoked token fails introspection; revocation beats expiry | `delegation-authority/tests` |
| Ledger down ⇒ mint refused, nothing persisted | `delegation-authority/tests` fail-closed case |
| Mint refused for unregistered / killed agents | `delegation-authority/tests` |

Declared-only items (not yet enforced): ledger WORM durability, signed
events, grantor identity verification, agents actually presenting tokens
(that is conformance-sentinel, Phase 2). Full tables in each service README.

## Demo output excerpt (delegation-authority demo — real spine on localhost)

```
=== 4. The ledger saw everything ===
  delegation.mint      agent=invoicing-agent hash=385cdf9b0fc3…
  delegation.revoke    agent=invoicing-agent hash=247bf2b8951e…
verify: {'ok': True, 'length': 2, 'first_break_index': None, 'reason': None}
```

Demo wall times: sealed-ledger ~6 s · agent-registry ~2.5 s ·
delegation-authority ~10 s (boots three real services).

## Known gaps carried forward

- OQ-1 (STATE.md): no inter-service authn in v0.1 — localhost trust,
  stated in every LIMITS section.
- Registry writes are not yet ledger events (wired in Phase 2 alongside the
  sentinel).
