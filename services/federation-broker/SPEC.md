# SPEC — federation-broker

**Purpose:** Gate inter-org agent traffic. Validate a counterparty's FIELD
manifest (valid, non-isolated, names us as a peer) and check the requested
scope + data class against a GC-registered federation contract. ALLOW/BLOCK
with clause ids; every crossing is a ledger event.

**Exec owners:** CIO / GC.

**FIELD letter:** F — Federation.

**v0.1 scope**
- SQLite contract store (`PUT /contracts/{id}`, one active per org).
- `POST /crossing`: six-step decision, first failing clause decides
  (I.manifest → F.isolated → F.peer ×4); `federation.allow|block` events.
- Home org via `FIELD_ORG_NAME`.
- CLI: `fedbroker add-contract | contracts | crossing | serve`.
- Demo: two local "orgs" — Borealis's billing agent crosses into Spin State
  with an in-contract request (ALLOW), then over-reaches (BLOCK).
- Adversarial test: valid-looking peer declaration on an invalid manifest
  is blocked before the peer entry is read.

**Explicit non-goals (v0.1)**
- No manifest signing/attestation (documented as the top LIMIT).
- No payload inspection; the envelope (scope + data class) is the unit.
- No outbound gating, no multi-contract negotiation, no mTLS.
