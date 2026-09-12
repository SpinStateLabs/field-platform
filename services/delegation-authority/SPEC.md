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
  (idempotent), POST `/introspect`, POST `/oauth/introspect`, `/health`.
- Registry check on mint (active agents only); ledger-first mint/revoke.
- CLI (talks to the running service): `delegation mint | revoke | introspect
  | list | serve`.
- Adversarial tests: expired and revoked tokens fail introspection; unknown
  ids fail closed; ledger-down mint refused with nothing persisted.

**v1.2 additions**
- **DOA roster** (`FIELD_DOA_ROSTER`, YAML, Pydantic `extra="forbid"`, new
  `delegation_authority/doa.py`). When the variable is set, mint checks, in
  order and all before the ledger write: roster load (missing/unreadable/
  invalid ⇒ 503); `granted_by` on the roster and `active` (else 403
  `D.grantor`); scope ⊆ that grantor's `allowed_scope` (else 403
  `D.grantor`); the agent manifest resolved from the registry record's
  `manifest_ref` — absent/missing/invalid ⇒ 422 `D.scope`, fail closed;
  scope ⊆ `manifest.delegation.scope` (else 422 `D.scope`); lifetime ≤
  `max_ttl_days` in both expiry forms (else 403 `D.grantor`). The
  `delegation.mint` ledger payload gains `doa_checked` and `doa_row`.
  Unset ⇒ v0.1 behaviour exactly, with `doa_checked: false`.
- **`POST /oauth/introspect`** — RFC 7662-shaped, `application/x-www-form-
  urlencoded` parsed with `urllib.parse.parse_qs` (no `python-multipart`
  dependency). Active ⇒ `{active, scope, scope_list, exp, iat, sub,
  client_id, token_type}`; revoked/expired/unknown ⇒ exactly
  `{"active": false}`. `POST /introspect` is unchanged.
- New field-core clause id `D.grantor`.
- CLI verb `delegation oauth-introspect`.

**Explicit non-goals (v0.1)**
- No cryptographic token format (JWT/JWS/DPoP) — introspection-only.
- No grantor authentication or approval workflow. The v1.2 DOA roster does
  **not** change this: it tests an exact-string membership of `granted_by`
  in an operator-maintained list. Nothing verifies that the caller is the
  human named, and `max_spend_usd` on a roster row is recorded on the ledger
  and never enforced.
- No scope semantics beyond exact strings.
- No auto-expiry sweeps (lifecycle-manager, Phase 4).
- `/oauth/introspect` is a response *shape*, not an OAuth 2.0 authorization
  server: no caller client-authentication beyond the platform shared secret,
  and `token_type: "opaque"` is this spec's word, not an RFC-registered one.
