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
- **`delegation doa check --roster --grantor --scope… --ttl-days
  [--manifest-ref] [--agent-id]`** (X1b) — pre-arm dry run of the DOA gate
  for a registered, active agent (the registry is not read). It builds
  `create_app()` with a registry stand-in (agent active, `manifest_ref` =
  `--manifest-ref` VERBATIM, alias `--manifest`, so a relative ref resolves
  against `FIELD_MANIFEST_DIR` as in the route), a ledger stand-in whose
  append raises, and a store that
  refuses to save, then calls the real `POST /tokens` handler with
  `FIELD_DOA_ROSTER=--roster` (restored afterwards). Reaching the ledger append
  with `doa_checked: true` ⇒ `ALLOW`, exit 0; an `HTTPException` ⇒ `REFUSED
  <clause> (<status>): <message>`, exit 1; anything else (invalid request,
  fault, handler returning, gate not run) ⇒ exit 2, no verdict. The gate rules
  are not duplicated: the verb and the route are the same code, and tests
  drive both with the same inputs. `doa.ROSTER_ENV` names the variable.
- `tools/generate_doa_roster.py` (X1b) writes a roster from an
  operator-supplied registry export, manifest directory and token export
  (`--tokens`, a saved `GET /delegation/tokens`), validated with `DoaRoster`
  before writing and reloaded with `load_roster` after; never `grantors: []`.
  Rows follow plan J9 only when `--tokens` is given: the grantor of every live
  (unrevoked, unexpired) token held by a registered non-retired agent, plus
  every manifest `identity.principal` and `delegation.granted_by` of those
  agents; scope = union of the named agents' manifest scopes. Without
  `--tokens`, live-token-only grantor strings are not rostered and the tool
  says so on stderr; their next renewal would be refused `403 D.grantor`.

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
