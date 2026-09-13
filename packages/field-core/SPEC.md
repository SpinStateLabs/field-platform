# SPEC — field-core

**Purpose:** Single source of truth for all FIELD Platform schemas: the FIELD
v1 manifest (Pydantic v2 models mirroring the shipped JSON Schema), manifest
validation at parity with the shipped `/field validate` plugin skill, ledger
event + hash-chain primitives, the delegation token model, and the conformance
verdict model.

**Exec owner:** CTO (schema governance is an engineering-integrity function).

**FIELD letter:** All five — this package encodes the letters the services
enforce.

**v0.1 scope**
- Pydantic models for the full manifest schema, `extra="forbid"` throughout.
- Vendored copies (verbatim) of `manifest-schema.json` and the four shipped
  templates from `SpinStateLabs/Force-Field`; parity tests pin the enums.
- `validate_manifest_data`: gap report (never a stack trace) with the skill's
  status taxonomy, critical gaps, and warnings.
- sha-256 linear hash chain: `make_event`, `compute_event_hash`, `verify_chain`
  with first-break reporting; `verify_chain(events, genesis=GENESIS_HASH)`
  verifies a chain whose first `prev_hash` is an earlier head.
- Ed25519 signing helpers (`field_core.signing`): canonical JSON bytes, keypair
  generation, sign/verify, and `key_fingerprint` (sha-256 over the raw 32-byte
  public key; non-Ed25519 keys refused).
- `DelegationToken` with ACTIVE/EXPIRED/REVOKED status; revocation beats expiry.
- `ConformanceVerdict` (ALLOW/BLOCK/ESCALATE) + stable clause-id registry.
- Typer CLI: `field validate | templates | verify-chain | version`.

**Explicit non-goals (v0.1)**
- No Merkle trees, no per-event signatures, no key management or custody
  (declared algorithms beyond sha-256 chaining are accepted syntactically, not
  implemented; the signing helpers sign whole documents).
- No storage, no HTTP *serving* — services own persistence and APIs.
  (Thin HTTP *clients* for the spine services live here so every enforcement
  service shares one fail-closed implementation; httpx is imported lazily and
  only when no client is injected.)
- No LLM anywhere in this package; everything is deterministic.
- No semantic interpretation of scope strings.
