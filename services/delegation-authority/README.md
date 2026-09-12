# delegation-authority

Scoped, expiring, revocable delegation tokens bound to a registered agent
and a **human grantor**. FIELD letter **D** (Delegation). Exec owner: **GC**.

An agent's authority is never ambient: it is a token someone minted, with a
scope, an expiry, and a revocation path — and every mint/revoke is a
sealed-ledger event *before* it takes effect.

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/tokens` | POST | Mint (`agent_id`, `granted_by`, `scope[]`, `ttl_seconds` xor `expires_at`) |
| `/tokens` | GET | List (filter `agent_id`) |
| `/tokens/{id}` | GET | Read one |
| `/tokens/{id}/revoke` | POST | Revoke (idempotent) |
| `/introspect` | POST | `{token_id}` → active / expired / revoked (unknown ⇒ inactive, fail closed) |
| `/oauth/introspect` | POST | RFC 7662-shaped; form-urlencoded `token=…` → `{active:…}` |
| `/health` | GET | Liveness + token count |

### `POST /oauth/introspect` — OAuth-style introspection

Body is `application/x-www-form-urlencoded` (`token=<token_id>`), parsed by
hand with `urllib.parse.parse_qs`: `python-multipart` is not installed, and a
FastAPI `Form()` parameter would make `create_app()` raise at route
registration. Missing/blank `token` ⇒ **400**.

An **active** token answers with exactly these keys:

```json
{"active": true, "scope": "read timesheets draft invoices",
 "scope_list": ["read timesheets", "draft invoices"],
 "exp": 1789000000, "iat": 1788996400,
 "sub": "invoicing-agent", "client_id": "invoicing-agent",
 "token_type": "opaque"}
```

- `scope` is RFC 7662's space-delimited string. **FIELD scopes contain spaces**
  ("read timesheets"), so that field alone is ambiguous and cannot be split
  back apart — `scope_list` (an RFC-permitted extension member) carries the
  exact scope strings and is the field to consume.
- `token_type: "opaque"` is **this spec's choice, not an RFC-registered
  value**. These tokens are database records, not bearer credentials.
- Revoked, expired and unknown tokens all answer **exactly** `{"active":
  false}` and nothing else — the response never says which, so it cannot be
  used to probe whether a token id ever existed.

The bespoke `POST /introspect` is unchanged and stays the canonical internal
shape (the conformance-sentinel and `delegation introspect` depend on it).

## CLI

```
delegation mint <agent-id> --granted-by G --scope S [--scope S2] [--ttl 3600]
delegation revoke <token-id>
delegation introspect <token-id>     # exit 1 unless ACTIVE
delegation oauth-introspect <token-id>  # RFC 7662 shape; exit 1 unless active
delegation list [--agent-id ID]
delegation serve [--port 8003]       # needs FIELD_LEDGER_URL + FIELD_REGISTRY_URL
```

## The DOA roster (`FIELD_DOA_ROSTER`)

Point `FIELD_DOA_ROSTER` at a YAML file and every mint is checked against it.
Leave it unset — the default in compose, fly and CI, **and on both estates
today** — and mint behaves exactly as it did before, recording
`doa_checked: false` on the ledger event.

```yaml
grantors:
  - grantor: Don Hagell, Spin State Labs   # must equal `granted_by` exactly
    allowed_scope: [read timesheets, draft invoice document]
    max_ttl_days: 30
    max_spend_usd: 500.0     # recorded on the ledger row, NEVER enforced
    active: true
```

Parsed by a Pydantic model with `extra="forbid"`: an unknown key is a 503 at
mint time, not a silently ignored line. Shipped example, matching both
`manifests/ssl-*.yaml` delegation scopes:
`manifests/doa-roster.example.yaml`.

Mint order when the roster is set (each step refuses before the next runs, and
all of them run **before** the ledger write):

1. **roster load** — missing, unreadable or invalid ⇒ `503`. A roster that
   cannot be read must never degrade into an unchecked mint.
2. `granted_by` on the roster, and `active` ⇒ else `403` `D.grantor`.
3. requested scope ⊆ that grantor's `allowed_scope` ⇒ else `403` `D.grantor`.
4. the agent's manifest, resolved from the registry record's `manifest_ref`
   by field-core's one resolver — **no ref, missing or invalid ⇒ `422`
   `D.scope`: fail closed.** An agent with no resolvable manifest cannot be
   minted for while a roster is in force.
5. requested scope ⊆ `manifest.delegation.scope` ⇒ else `422` `D.scope`. The
   roster widens nothing: a scope must clear both lists.
6. lifetime ≤ `max_ttl_days`, checked on the computed expiry so both the
   `ttl_seconds` and the `expires_at` form are covered ⇒ else `403`
   `D.grantor`.

Refusals carry `{"clause_id": ..., "message": ...}` in `detail`, so an
incident replay can point at the clause that fired.

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Tokens bind to a registered, **active** agent | **Enforced in code** | mint checks the registry; unregistered → 404, killed → 409 |
| Expired tokens fail introspection | **Enforced in code** | adversarial test |
| Revoked tokens fail introspection; revocation beats expiry | **Enforced in code** | adversarial test |
| Unknown token ids are inactive | **Enforced in code** | fail closed |
| Every mint/revoke is a ledger event **before** it takes effect | **Enforced in code** | ledger-first ordering; ledger down ⇒ 502, no token (adversarial test) |
| Mint refuses off-roster grantors, scopes and TTLs | **Enforced in code when `FIELD_DOA_ROSTER` is set** (unset on both estates today) | roster missing/unreadable/invalid ⇒ 503 before any ledger write; grantor absent or `active: false`, scope beyond that grantor's `allowed_scope`, lifetime beyond `max_ttl_days` (both expiry forms) ⇒ 403 `D.grantor`; scope beyond the agent manifest's `delegation.scope`, or no resolvable manifest ⇒ 422 `D.scope` (fail closed); adversarial tests |
| The caller **is** the named grantor | **Declared only** | `granted_by` is not authenticated; the roster proves membership of a string in a YAML list, not identity. SPEC's "no grantor authentication" non-goal still holds |
| `max_spend_usd` on a roster row | **Declared only** | recorded in the `delegation.mint` ledger payload (`doa_row`), never enforced here — spend caps are spend-governor's |
| Revoked / expired / unknown tokens leak no reason at `/oauth/introspect` | **Enforced in code** | all three return exactly `{"active": false}`; adversarial test asserts the whole body |
| Agents actually *present* tokens when acting | **Declared only** | that check is conformance-sentinel's job (Phase 2) |
| Scope strings carry semantics | **Declared only** | exact-string matching; meaning lives with the operator |

## LIMITS

- Tokens are database records, not signed bearer credentials (no JWT/JWS in
  v0.1) — introspection is the only source of truth, so the authority
  service must be reachable at decision time.
- A mint acknowledged by the ledger but not yet persisted (crash between
  the two writes) yields a ledger event for a token that never existed —
  visible in audit as a mint with no matching introspections. The reverse
  (token without ledger event) cannot happen.
- The DOA roster is a membership list, not an identity check. It refuses a
  `granted_by` string that is not on the list; it cannot tell whether the
  caller is that person. Anyone who can reach the mint endpoint can type a
  rostered grantor's name.
- `FIELD_DOA_ROSTER` is **unset** in compose, fly and CI, and both estates run
  pre-v1.2 images: the roster gate is test- and CI-proven only, and stays
  *Declared* on the estates until Don deploys a roster file and the env var.
- `max_spend_usd` is recorded, never enforced. Nothing in this service reads a
  spend total.
- `/oauth/introspect` is RFC 7662-*shaped*, not an OAuth 2.0 server: no
  client authentication of the introspecting caller beyond the platform's
  shared-secret header, no `username`/`aud`/`iss` members, and `token_type`
  is not an RFC-registered value.
- API authn: optional shared-secret header (`FIELD_SHARED_SECRET` → `x-field-auth`), enforced by middleware when set; off by default for local demos. `/health` stays open for probes. Transport is plain HTTP — TLS belongs to a fronting proxy in real deployments.
