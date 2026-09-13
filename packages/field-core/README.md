# field-core

Single source of truth for FIELD Platform schemas (Force Field Protocol).
Every service in `services/` imports these models; no service redefines schema.

## What's here

| Module | Contents |
|---|---|
| `field_core.manifest` | Pydantic v2 models mirroring the FIELD v1 manifest JSON Schema (vendored in `schema/`) |
| `field_core.validation` | `field validate` — parity with the shipped Force-Field plugin skill (VALID / VALID_WITH_WARNINGS / INVALID, critical gaps, warnings) |
| `field_core.ledger` | Ledger event model + sha-256 hash-chain primitives (`make_event`, `verify_chain(events, genesis=GENESIS_HASH)` — `genesis` is the `prev_hash` the first event must carry, so a chain that continues an earlier head can be verified) |
| `field_core.signing` | Ed25519 helpers: `canonical_manifest_bytes`, `generate_keypair`, `sign_manifest`, `verify_manifest`, and `key_fingerprint(public_key_pem)` — sha-256 hex over the raw 32-byte Ed25519 public key (non-Ed25519 keys raise `ValueError`) |
| `field_core.delegation` | Delegation token model — scoped, expiring, revocable |
| `field_core.conformance` | ALLOW / BLOCK / ESCALATE verdict model + stable clause-id registry |
| `field_core.templates_api` | The four shipped manifest templates, vendored verbatim |
| `field_core.clients` | HTTP clients for the platform services, plus the **shared manifest resolver** (v1.2 B0): `ManifestResolver`, `resolve_manifest`, `resolve_manifest_detail` — `FIELD_MANIFEST_DIR`, mtime-cached, `None` on missing or invalid |

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
| A chain continuing an earlier head verifies only against that head | **Enforced in code** | `verify_chain(events, genesis)`; `tests/test_verify_chain_genesis.py` (verifies with its genesis, breaks at index 0 without it, first-break index and reason under a custom genesis) |
| A key fingerprint is sha-256 over the raw Ed25519 key, independent of its PEM/DER encoding | **Enforced in code** | `key_fingerprint` hashes `public_bytes_raw()` and refuses non-Ed25519 keys (X25519 included); `tests/test_key_fingerprint.py` pins the RFC 8032 test-vector key's value and the private key's public half |
| Token expiry / revocation semantics | **Enforced in code** | `DelegationToken.status()`; revocation wins over expiry |
| Ledger durability (nobody deletes the whole file) | **Declared only** | Hash chains prove mutation, not deletion. WORM/append-only storage is deployment responsibility |
| Seal algorithms other than sha-256 chaining (merkle, ed25519) | **Declared only** | v0.1 implements sha-256 linear chaining; the manifest may declare stronger schemes the platform does not yet implement |
| Scope strings mean what they say (e.g. "read-only") | **Declared only** | Scopes are matched as strings; semantics live with the operator |
| Anything a manifest *declares* about runtime behavior | **Declared only** | Enforcement happens in the Phase 1–2 services, not in this package |

## LIMITS

- v0.1 ledger primitive is a **linear sha-256 hash chain**, not a Merkle tree,
  and events are **not signed** — the chain proves internal consistency, not
  authorship. `ed25519-signed-chain` is accepted as a *declared* algorithm but
  per-event signing is not implemented (F2). `field_core.signing` signs
  manifests and whole documents (e.g. the ledger's export bundle), not events.
- `verify_chain(events, genesis)` trusts the `genesis` it is given: a chain
  checked against a head the caller made up proves nothing about earlier
  history. `first_break_index` is the index within `events`, not a global one.
- A key fingerprint identifies a key; it does not make it trusted. Whoever
  verifies must obtain the public key out-of-band.
- `validate` warns on `REPLACE-ME` placeholders but cannot know whether a
  resolved value is *true* (a real kill-switch endpoint vs. a plausible string).
- Scope matching is exact-string; no glob/hierarchy semantics in v0.1.
- Expiry parsing accepts ISO 8601 only; naive datetimes are assumed UTC.
