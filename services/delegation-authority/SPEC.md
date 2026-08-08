# SPEC — delegation-authority

**Purpose:** Mint, list, revoke, and introspect delegation tokens — the
platform's concrete form of the manifest's D section. A token binds a
registered agent to a human grantor, a scope list, and an expiry, and can be
revoked at any time. Every mint and revoke is written to the sealed ledger
before it takes effect (fail closed).

**Exec owner:** GC (General Counsel) — delegated authority is a legal
construct before it is a technical one.

**FIELD letter:** D — Delegation.

**v0.1 scope**
- SQLite token store; tokens are field-core `DelegationToken` records.
- FastAPI: POST/GET `/tokens`, GET `/tokens/{id}`, POST `/tokens/{id}/revoke`
  (idempotent), POST `/introspect`, `/health`.
- Registry check on mint (active agents only); ledger-first mint/revoke.
- CLI (talks to the running service): `delegation mint | revoke | introspect
  | list | serve`.
- Adversarial tests: expired and revoked tokens fail introspection; unknown
  ids fail closed; ledger-down mint refused with nothing persisted.

**Explicit non-goals (v0.1)**
- No cryptographic token format (JWT/JWS/DPoP) — introspection-only.
- No grantor authentication or approval workflow.
- No scope semantics beyond exact strings.
- No auto-expiry sweeps (lifecycle-manager, Phase 4).
