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
| `field_core.buildinfo` | `build_sha()` — `FIELD_BUILD_SHA`, read per call; unset or blank is `unknown`. Every served service's `/health` reports it as `build_sha` (v1.2 Phase C) |
| `field_core.delegation` | Delegation token model — scoped, expiring, revocable |
| `field_core.conformance` | ALLOW / BLOCK / ESCALATE verdict model + stable clause-id registry |
| `field_core.templates_api` | The four shipped manifest templates, vendored verbatim |
| `field_core.clients` | HTTP clients for the platform services (`LedgerClient.retention_check()` — C2 `GET /retention/check`; a transport error or any non-200 raises `LedgerUnreachableError`, `tests/test_ledger_client_retention_check.py`), plus the **shared manifest resolver** (v1.2 B0): `ManifestResolver`, `resolve_manifest`, `resolve_manifest_detail` — `FIELD_MANIFEST_DIR`, mtime-cached, `None` on missing or invalid |
| `field_core.llm` | Where the platform's own LLM calls go (v1.2 D2e): `anthropic_base_url()` = `FORCE_GATEWAY_URL` > `ANTHROPIC_BASE_URL` > `https://api.anthropic.com` (blank = unset, trailing slashes stripped); `anthropic_headers(key)` = `x-api-key` + `anthropic-version`, plus — only when `FORCE_GATEWAY_URL` is the target — `x-force-passthrough: judge` and `auth_headers()`. Used by the sentinel judge, the crosswalk suggester and the gateway hygiene judge; NOT by the gateway's own upstream |

## CLI

```
field validate [manifest.yaml]     # parity with /field validate; exit 1 on INVALID
field templates [--show NAME]      # list or print the four shipped templates
field verify-chain events.jsonl [--genesis HASH]   # walk ONE file; report first break
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
| Every served service's `/health` carries `build_sha`: `FIELD_BUILD_SHA` verbatim (surrounding whitespace stripped), `unknown` when unset or blank, read per request | **Enforced in code** | `field_core.buildinfo.build_sha()` called by all thirteen `/health` handlers; `tools/tests/test_build_sha_health.py` drives each real `create_app()` (verbatim, `unknown`, set after app creation) and fails for exactly the service whose key is removed (mutation-checked on ops-console); `tests/test_buildinfo.py` pins the helper |
| `build_sha` names the source actually installed in the image | **Declared only** | It is a label: the builder passes it as a Docker build arg and nothing hashes the installed code. `estate_probe.py health --expect-build-sha` catches a container running a different label (one not recreated), not a build given the wrong label. The deploy instructions say to build from a clean worktree at that SHA; nothing checks that they were followed |
| Ledger durability (nobody deletes the whole file) | **Declared only** | Hash chains prove mutation, not deletion. WORM/append-only storage is deployment responsibility |
| Seal algorithms other than sha-256 chaining (merkle, ed25519) | **Declared only** | v0.1 implements sha-256 linear chaining; the manifest may declare stronger schemes the platform does not yet implement |
| Scope strings mean what they say (e.g. "read-only") | **Declared only** | Scopes are matched as strings; semantics live with the operator |
| The platform LLM base URL is `FORCE_GATEWAY_URL` > `ANTHROPIC_BASE_URL` > default, read per call | **Enforced in code** | `field_core.llm`; `tests/test_llm.py` (precedence, blank values fall through, trailing slash, per-call read); the three callers are pinned in `services/force-gateway/tests/test_d2_llm_callers.py` |
| The shared secret and the passthrough header are sent only to `FORCE_GATEWAY_URL`, never to `ANTHROPIC_BASE_URL` or the Anthropic host | **Enforced in code** | `anthropic_headers` adds them only when `FORCE_GATEWAY_URL` decides the target (`tests/test_llm.py`) |
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
- `field verify-chain FILE` is single-file by design. On the open segment of a
  rotated sealed ledger (a `<stem>.segments.journal` beside it) it reports
  `TAMPERED — link break at index 0` and exits 1, because that segment's first
  event continues the closed segment; it also prints a note to stderr naming
  `ledger verify --path FILE`, which walks every segment. `--genesis HASH`
  verifies one segment from the previous segment's head. On a never-rotated
  file its output is unchanged.
- `ChainVerification` serialises four keys for a single-file chain; the four
  C2 keys (`segments`, `archived_segments`, `verified_events`,
  `break_segment`) appear only when a segmented ledger sets them
  (`tests/test_chain_verification_c2.py`).
- A key fingerprint identifies a key; it does not make it trusted. Whoever
  verifies must obtain the public key out-of-band.
- `validate` warns on `REPLACE-ME` placeholders but cannot know whether a
  resolved value is *true* (a real kill-switch endpoint vs. a plausible string).
- Scope matching is exact-string; no glob/hierarchy semantics in v0.1.
- Expiry parsing accepts ISO 8601 only; naive datetimes are assumed UTC.
- `field_core.llm` cannot tell whether an `ANTHROPIC_BASE_URL` is a force-gateway:
  a caller pointed at a gateway that way gets no `x-field-auth` (401 on a
  secret estate) and no passthrough header (its calls are instrumented as
  hygiene traffic). Platform callers route through the gateway with
  `FORCE_GATEWAY_URL`; `FIELD_GATEWAY_URL` remains the `forcegw` CLI target.
