# agent-registry

Agent identity records + shadow-agent discovery. FIELD letter **I**
(Identity). Exec owner: **CIO**.

If it isn't in the registry, the platform treats it as ungoverned. The
discovery scanner turns two artifacts every IT org already has — an n8n
workflow export and a service-account inventory — into a review queue of
"unregistered agent candidates."

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/agents` | POST | Register an agent (id, name, human owner, domain, manifest ref) |
| `/agents` | GET | List (filter by `status`, `domain`) |
| `/agents/{id}` | GET / PATCH | Read / update (incl. `status`: active·killed·retired) |
| `/discover` | POST | Scan `n8n_export` JSON and/or `accounts_csv` text for shadow agents |
| `/health` | GET | Liveness + agent count |

## CLI

```
registry add <agent-id> --name N --owner O [--domain D] [--manifest-ref R]
registry list [--status S] [--domain D]
registry scan [--n8n export.json] [--accounts accounts.csv]   # exit 3 if candidates found
registry serve [--port 8001]
```

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| One record per agent id; well-formed slugs; human owner required | **Enforced in code** | Pydantic + SQLite primary key |
| Status transitions persist and are queryable (kill-switch reads these) | **Enforced in code** | SQLite store |
| AI workflows/accounts in scanned artifacts surface unless registered | **Enforced in code** | deterministic node-type + name-pattern scanner (see adversarial test: renaming a workflow doesn't hide it) |
| The registry knows about *all* agents in the org | **Declared only** | discovery covers only the artifacts you feed it; an agent outside n8n and the account inventory is invisible |
| `manifest_ref` points at a valid manifest | **Declared only** | v0.1 stores the reference; validation is `field validate`'s job |
| `owner` is a real, current human | **Declared only** | roster reconciliation is lifecycle-manager's job (Phase 4) |

## LIMITS

- Discovery is a **labeled heuristic** (regex/string matching, no LLM):
  expect false positives (e.g. non-AI automation accounts) — it produces a
  review queue, not a verdict. False negatives are possible if an AI node
  type contains none of the known markers.
- Name matching between candidates and registered agents is normalized
  substring matching — a completely renamed shadow account with no overlap
  to a registered name will (correctly) surface, but a shadow account named
  *like* a registered agent will be missed. Registration hygiene matters.
- No API authentication in v0.1 — localhost trust (STATE.md OQ-1).
- Registry writes are not yet ledger events (Phase 2 wiring).
