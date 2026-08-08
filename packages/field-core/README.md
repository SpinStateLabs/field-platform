# field-core

Single source of truth for FIELD Platform schemas (Force Field Protocol).
Every service in `services/` imports these models; no service redefines schema.

## What's here

| Module | Contents |
|---|---|
| `field_core.manifest` | Pydantic v2 models mirroring the FIELD v1 manifest JSON Schema (vendored in `schema/`) |
| `field_core.validation` | `field validate` — parity with the shipped Force-Field plugin skill (VALID / VALID_WITH_WARNINGS / INVALID, critical gaps, warnings) |
| `field_core.ledger` | Ledger event model + sha-256 hash-chain primitives (`make_event`, `verify_chain`) |
| `field_core.delegation` | Delegation token model — scoped, expiring, revocable |
| `field_core.conformance` | ALLOW / BLOCK / ESCALATE verdict model + stable clause-id registry |
| `field_core.templates_api` | The four shipped manifest templates, vendored verbatim |

## CLI

```
field validate [manifest.yaml]     # parity with /field validate; exit 1 on INVALID
field templates [--show NAME]      # list or print the four shipped templates
field verify-chain events.jsonl    # walk a hash chain; report first break
field version
```

## Enforced vs. Declared

A governance product that overclaims has already failed. This table is exact.

| Guarantee | Status | How |
|---|---|---|
| Manifest structure (5 sections, required fields, closed enums) | **Enforced in code** | Pydantic `extra="forbid"` models; invalid manifests do not parse |
| `cryptographic_seal: true` is constant; `"none"` is not a seal algorithm | **Enforced in code** | `Literal[True]` + closed `Literal` enum |
| Non-isolated agents must declare peers | **Enforced in code** | model validator |
| Tamper-evidence of a ledger chain | **Enforced in code** | sha-256 chain; `verify_chain` reports first break (see adversarial tests) |
| Token expiry / revocation semantics | **Enforced in code** | `DelegationToken.status()`; revocation wins over expiry |
| Ledger durability (nobody deletes the whole file) | **Declared only** | Hash chains prove mutation, not deletion. WORM/append-only storage is deployment responsibility |
| Seal algorithms other than sha-256 chaining (merkle, ed25519) | **Declared only** | v0.1 implements sha-256 linear chaining; the manifest may declare stronger schemes the platform does not yet implement |
| Scope strings mean what they say (e.g. "read-only") | **Declared only** | Scopes are matched as strings; semantics live with the operator |
| Anything a manifest *declares* about runtime behavior | **Declared only** | Enforcement happens in the Phase 1–2 services, not in this package |

## LIMITS

- v0.1 ledger primitive is a **linear sha-256 hash chain**, not a Merkle tree,
  and events are **not signed** — the chain proves internal consistency, not
  authorship. `ed25519-signed-chain` is accepted as a *declared* algorithm but
  signing is not implemented in this package.
- `validate` warns on `REPLACE-ME` placeholders but cannot know whether a
  resolved value is *true* (a real kill-switch endpoint vs. a plausible string).
- Scope matching is exact-string; no glob/hierarchy semantics in v0.1.
- Expiry parsing accepts ISO 8601 only; naive datetimes are assumed UTC.
