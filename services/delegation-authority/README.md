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
delegation doa check --roster FILE --grantor G --scope S [--scope S ...] \
  --ttl-days N [--manifest-ref REF] [--agent-id ID]   # dry run; exit 0 ALLOW, 1 REFUSED, 2 no verdict
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
    max_spend_usd: 500.0     # stamped on the token; the sentinel enforces it (E.spend_cap)
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

### Pre-arm dry run — `delegation doa check`

Before `FIELD_DOA_ROSTER` is armed, run the gate for every real renewal with
its real grantor, scope and TTL — in-container, against the roster file and the
registry record's `manifest_ref`, pasted exactly as the record has it:

```
delegation doa check --roster /data/doa-roster.yaml \
  --grantor "Don Hagell, Spin State Labs" \
  --scope "read timesheets" --scope "draft invoice document" \
  --ttl-days 30 --manifest-ref /data/manifests/ssl-invoicing-agent.yaml
```

It prints `ALLOW …` (exit 0), or `REFUSED <clause> (<status>): <message>`
(exit 1) with the route's own clause id and message, or `ERROR … no verdict`
(exit 2: an invalid request, a fault, or a gate that did not run).

It does **not** re-implement the gate. It builds the real app and calls the real
`POST /tokens` handler in-process with three stand-ins: a registry that answers
"registered and active" with `--manifest-ref` as the `manifest_ref`, a ledger whose
first append stops the handler, and a token store that refuses to save. The
handler appends to the ledger only after its last refusal clause, so reaching
that append is the ALLOW — and only when the would-be ledger payload says
`doa_checked: true`. `FIELD_DOA_ROSTER` is set to `--roster` for the call and
restored exactly afterwards. No token, no ledger event, no file, no connection.

- `--manifest-ref` (alias `--manifest`) is handed to the route's resolver
  unchanged: a relative ref resolves against `FIELD_MANIFEST_DIR` (or the
  working directory when that is unset) exactly as the route resolves the
  registry's ref — never against the verb's own working directory first.
- `--manifest-ref` omitted = an agent with no `manifest_ref`, which the gate
  refuses (`422 D.scope … (no_ref)`), exactly as a mint would.
- `--agent-id` only changes the id in messages (default: the ref's file
  stem, which is the agent id for every manifest in `manifests/`).

### Generating a roster — `tools/generate_doa_roster.py`

```
python tools/generate_doa_roster.py --registry agents.json --manifests DIR \
  --tokens tokens.json --out doa-roster.yaml [--max-ttl-days 30] [--skip-unresolved]
```

Inputs are supplied by the operator — an in-estate `GET /registry/agents` and
`GET /delegation/tokens`, each saved to a file, and a directory of the agents'
manifests; the tool opens no connection. Rows (plan J9, which needs `--tokens`),
over registered agents that are not `retired`:

- one per distinct `granted_by` of a **live** token (not revoked, not expired
  when the tool runs) held by such an agent — a string no manifest names is
  printed as `[token-only: …]`;
- one per distinct manifest `identity.principal` and one per distinct manifest
  `delegation.granted_by` (the canary's grantor arrives this way).

Each row's `allowed_scope` is the union of `delegation.scope` over the
manifests of the agents it names (in the manifest, or as the grantor of a live
token they hold); `max_ttl_days` 30 by default; `active: true`. A record's
`manifest_ref` is resolved by file name inside `--manifests` with field-core's
resolver. It refuses (exit 2, nothing written) on bad registry or token inputs,
an unresolvable manifest (unless `--skip-unresolved`, which names each skip),
an empty roster (with or without `--skip-unresolved`), or a roster this
service's model rejects — validated before writing and again by reloading the
written file. Without `--tokens` it still writes a roster but says, on stderr,
that grantor strings found only on live tokens are **not** rostered; a live
token grantor whose holders have no resolvable manifest is named and not
rostered. `doa check` every real renewal either way.

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Tokens bind to a registered, **active** agent | **Enforced in code** | mint checks the registry; unregistered → 404, killed → 409 |
| Expired tokens fail introspection | **Enforced in code** | adversarial test |
| Revoked tokens fail introspection; revocation beats expiry | **Enforced in code** | adversarial test |
| Unknown token ids are inactive | **Enforced in code** | fail closed |
| Every mint/revoke is a ledger event **before** it takes effect | **Enforced in code** | ledger-first ordering; ledger down ⇒ 502, no token (adversarial test) |
| Mint refuses off-roster grantors, scopes and TTLs | **Enforced in code when `FIELD_DOA_ROSTER` is set** (unset on both estates today) | roster missing/unreadable/invalid ⇒ 503 before any ledger write; grantor absent or `active: false`, scope beyond that grantor's `allowed_scope`, lifetime beyond `max_ttl_days` (both expiry forms) ⇒ 403 `D.grantor`; scope beyond the agent manifest's `delegation.scope`, or no resolvable manifest ⇒ 422 `D.scope` (fail closed); adversarial tests |
| `delegation doa check` says what the mint route's DOA roster gate would say **for a registered, active agent whose registry `manifest_ref` is the `--manifest-ref` given**, and mints nothing | **Enforced in code** for that agent state only — the registry is not read (see LIMITS) | it calls the route's own handler (a test patches the route module's resolver and the verb's output changes); every refusal clause, the 503s and ALLOW are driven through the route over TestClient and through the verb with the same files, and must agree on status, clause and message (`tests/test_doa_check_verb.py`); a relative `manifest_ref` resolves against `FIELD_MANIFEST_DIR` in both (`test_a_relative_manifest_ref_resolves_like_the_route`); ALLOW requires `doa_checked: true`; a fault, or a handler that never reaches the ledger, is exit 2 and never ALLOW or REFUSED; run with the token store, the real clients and httpx booby-trapped it still answers and writes nothing; `FIELD_DOA_ROSTER` is restored; each guard mutation-checked |
| `tools/generate_doa_roster.py` rosters exactly the manifest grantors and principals of registered non-retired agents, plus (with `--tokens`) the grantor of every live token they hold | **Enforced in code** | `tools/tests/test_generate_doa_roster.py`: retired agents and unregistered manifests contribute nothing; a live-token-only grantor is rostered with its holder's manifest scope, while revoked, expired, retired-holder and unregistered-holder tokens add nothing; the plan J9 GB10 shape (volatility-trader's `Don Hagell` token) gets both of Don's rows and its renewal ALLOWs; without `--tokens` the gap is said on stderr; scope union; TTL flag; empty roster (also under `--skip-unresolved`), unresolved manifests, malformed token files and model-invalid rosters refused with nothing written; output loads with `load_roster` and drives the real gate; each guard mutation-checked |
| The caller **is** the named grantor | **Declared only** | `granted_by` is not authenticated; the roster proves membership of a string in a YAML list, not identity. SPEC's "no grantor authentication" non-goal still holds |
| `max_spend_usd` on the matched roster row is stamped on the token at mint and returned by `/introspect` with `issued_at` (v1.2 D1e) | **Enforced in code when `FIELD_DOA_ROSTER` is set** | still recorded in the `delegation.mint` payload (`doa_row`); `tests/test_d1e_token_ceiling.py`: a rostered mint stamps it (0 included) and `GET /tokens`, `/tokens/{id}` and `/introspect` return it; a row without the key, or the roster unset, stamps nothing and the token JSON keeps its pre-D1e keys; revoke keeps it and a later save cannot change or remove it; a pre-D1e `tokens.sqlite3` opens and reads null, and the pre-D1e image's positional INSERT still mints and revokes after this image opened the file |
| A token's `max_spend_usd` bounds the agent's spend under it | **Enforced in code by conformance-sentinel, not here** | this service stamps and serves the ceiling and never reads a spend total; the sentinel BLOCKs `E.spend_cap` (its README; end to end, no monkeypatch, in `services/conformance-sentinel/tests/test_throttle_metering.py::test_a_rostered_tokens_max_spend_usd_blocks_spend_cap_end_to_end`) |
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
- `FIELD_DOA_ROSTER` is **unset** in compose, fly and CI. The gate's code is
  deployed on both estates (X0, 2026-09-12) but not armed: it is test- and
  CI-proven only, and stays *Declared* on the estates until arming step A3
  places a roster file and sets the variable.
- `delegation doa check` evaluates the DOA gate only. It does not read the
  registry: the agent is taken as registered and active, with `--manifest-ref`
  as its `manifest_ref`. So an unregistered agent (404), a killed agent (409),
  a record whose real `manifest_ref` differs from the one pasted (for example
  a stale ref the route would answer `422 D.scope (missing)`), and the ledger
  write (502) are not evaluated: ALLOW means "the roster gate passes for that
  agent state", not "a live mint will succeed". TTLs are whole days.
  Without `--agent-id`, an empty `--manifest-ref ""` gives exit 2 (no
  verdict) where the route answers `422 D.scope (no_ref)`; never an ALLOW.
- `tools/generate_doa_roster.py` writes a roster from the inputs it is given;
  it cannot know whether they are current (a token minted after
  `tokens.json` was saved is not seen). Without `--tokens` it does not
  implement plan J9's live-token row source. Review the file before arming it.
- `max_spend_usd` is stamped and served, never enforced HERE: nothing in this
  service reads a spend total; conformance-sentinel enforces it, and only for
  a caller that presents the token to `/check`. It comes only from the roster
  row matched at mint (roster armed), so a token minted with the roster unset
  has no ceiling, and a roster edit never changes a token already minted
  (renewal re-stamps). The value is stored in a side table
  (`token_spend_ceilings`), created at open, which a pre-D1e image never reads:
  after an image rollback its mints carry no ceiling and the ones already
  stamped are not served until the D1e image is back.
- `/oauth/introspect` is RFC 7662-*shaped*, not an OAuth 2.0 server: no
  client authentication of the introspecting caller beyond the platform's
  shared-secret header, no `username`/`aud`/`iss` members, and `token_type`
  is not an RFC-registered value.
- API authn: optional shared-secret header (`FIELD_SHARED_SECRET` → `x-field-auth`), enforced by middleware when set; off by default for local demos. `/health` stays open for probes. Transport is plain HTTP — TLS belongs to a fronting proxy in real deployments.
