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
| `/health` | GET | Liveness + token count |

## CLI

```
delegation mint <agent-id> --granted-by G --scope S [--scope S2] [--ttl 3600]
delegation revoke <token-id>
delegation introspect <token-id>     # exit 1 unless ACTIVE
delegation list [--agent-id ID]
delegation serve [--port 8003]       # needs FIELD_LEDGER_URL + FIELD_REGISTRY_URL
```

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Tokens bind to a registered, **active** agent | **Enforced in code** | mint checks the registry; unregistered → 404, killed → 409 |
| Expired tokens fail introspection | **Enforced in code** | adversarial test |
| Revoked tokens fail introspection; revocation beats expiry | **Enforced in code** | adversarial test |
| Unknown token ids are inactive | **Enforced in code** | fail closed |
| Every mint/revoke is a ledger event **before** it takes effect | **Enforced in code** | ledger-first ordering; ledger down ⇒ 502, no token (adversarial test) |
| Grantor is a real human with authority to grant | **Declared only** | `granted_by` is a string; identity-provider integration is out of v0.1 scope |
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
- API authn: optional shared-secret header (`FIELD_SHARED_SECRET` → `x-field-auth`), enforced by middleware when set; off by default for local demos. `/health` stays open for probes. Transport is plain HTTP — TLS belongs to a fronting proxy in real deployments.
