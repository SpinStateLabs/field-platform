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
| `/agents/{id}/attest` | POST | Record a human re-attestation: body `{attested_by}` (stripped; blank ⇒ 422, unknown agent ⇒ 404) |
| `/discover` | POST | Scan `n8n_export` JSON and/or `accounts_csv` text for shadow agents |
| `/health` | GET | Liveness + agent count |

## CLI

```
registry add <agent-id> --name N --owner O [--domain D] [--manifest-ref R]
registry list [--status S] [--domain D]
registry attest <agent-id> --by NAME                            # sets attested_at/attested_by
registry scan [--n8n export.json] [--accounts accounts.csv]   # exit 3 if candidates found
registry serve [--port 8001]
```

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| One record per agent id; well-formed slugs; human owner required | **Enforced in code** | Pydantic + SQLite primary key. `name` and `owner` are `min_length=1` on create AND on PATCH: an empty value is a 422 at the request model, the row unchanged and no ledger note (`tests/test_registry_update_validation.py`). Non-empty only: a whitespace-only value is accepted |
| Status transitions persist and are queryable (kill-switch reads these) | **Enforced in code** | SQLite store. A PATCH writes only the fields it carries, reading and writing in one lock hold and one `BEGIN IMMEDIATE` transaction, so a concurrent PATCH of another field cannot write an old `status` back over a kill. Two connections to the same file are covered too. A kill raced by edits ledgers exactly one `registry.status_changed` (`tests/test_registry_update_atomicity.py`) |
| AI workflows/accounts in scanned artifacts surface unless registered | **Enforced in code** | deterministic node-type + name-pattern scanner (see adversarial test: renaming a workflow doesn't hide it) |
| The registry knows about *all* agents in the org | **Declared only** | discovery covers only the artifacts you feed it; an agent outside n8n and the account inventory is invisible |
| `manifest_ref` points at a valid manifest | **Declared only** | v0.1 stores the reference; validation is `field validate`'s job |
| `attested_at` moves only on an explicit attestation — no PATCH can forge or reset it | **Enforced in code** | `AgentUpdate` has neither field and is `extra='forbid'`: a PATCH carrying `attested_by`/`attested_at` is a 422, and a kill/revive cycle leaves `attested_at` untouched (adversarial tests) |
| `attested_by` is the human who attested | **Declared only** | a recorded string, not an authenticated identity — the registry takes the caller's word for the name |
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
- **A retirement is final at the kill-switch, not at the registry.**
  `PATCH /agents/{id}` with `{"status": "active"}` puts a retired agent back
  to `active`, returns 200 and ledgers a plain `registry.status_changed`.
  The kill-switch's four 409s (`/kill`, `/revive`, `/kill/domain`, `/drill`)
  close the *operator console* path, which is the one a CISO clicks at 2 a.m.
  The registry route stays open on purpose — it is the correction path for a
  decommission made in error — so treat `retired` as reversible by whoever
  can reach the registry API directly, and read the ledger to see it happen.
- API authn: optional shared-secret header (`FIELD_SHARED_SECRET` → `x-field-auth`), enforced by middleware when set; off by default for local demos. `/health` stays open for probes. Transport is plain HTTP — TLS belongs to a fronting proxy in real deployments.
- The SQLite schema is created with `CREATE TABLE IF NOT EXISTS`, so new
  columns reach a **persisted** database only through the `ALTER TABLE`
  migration in `RegistryStore.__init__` (`_MIGRATIONS`). It is
  **forward-only**: an older image can still read the table (it ignores
  `attested_at`/`attested_by`), but there is no down-migration — back up
  `/data/registry` before first opening an estate database with this code.
- Registry writes **made over HTTP** are ledger events
  (`registry.registered` / `registry.status_changed` / `registry.updated` /
  `registry.attested`) when a ledger is configured — best-effort by design:
  identity infrastructure stays up during audit outages, and the gap is
  visible as missing events.
- **The CLI writes SQLite directly, so only `registry attest` is ledgered.**
  `registry add` and any other local edit of the database file leave no
  event. `attest` is the exception because `attested_at` is the only field
  that clears a `lifecycle.reattestation_due` escalation: it appends
  `registry.attested` itself, exits **3** if a configured ledger refuses, and
  says so out loud when `FIELD_LEDGER_URL` is unset. Anyone with write access
  to the registry volume can still edit the file with `sqlite3` and leave no
  trace — the ledger records what the platform did, not what the filesystem
  allows.
- **A rollback cannot register new agents.** The migration is forward-only, so
  an older image reading a migrated database is fine (it selects by name) but
  its positional `INSERT` hits `table agents has 10 columns but 8 values were
  supplied` — `POST /agents` 500s until the image is rolled forward again.
