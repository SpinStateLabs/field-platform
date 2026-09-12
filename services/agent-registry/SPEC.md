# SPEC — agent-registry

**Purpose:** System of record for agent identity: who each agent is, which
human owns it, what domain it operates in, where its FIELD manifest lives,
and whether it is active, killed, or retired. Plus shadow-agent discovery:
scan an n8n workflow export and a service-account CSV for AI workloads that
match no registered agent.

**Exec owner:** CIO.

**FIELD letter:** I — Identity.

**v0.1 scope**
- SQLite store (stdlib sqlite3), slug-validated agent ids, human owner
  required, domain field (kill-switch kills by domain in Phase 2).
- FastAPI: `/agents` CRUD (POST/GET/PATCH), `/discover`, `/health`.
- CLI: `registry add | list | scan | serve` (scan exits 3 when candidates
  found, for CI wiring).
- Deterministic discovery heuristic: n8n AI-node-type markers +
  service-account naming patterns; registered agents filtered by normalized
  substring match; adversarial test proves renamed workflows still surface.

**v1.2 additions (B4)**
- `attested_at` / `attested_by` on `AgentRecord` **only** — deliberately
  absent from `AgentCreate` and `AgentUpdate` so `extra='forbid'` makes a
  PATCH that tries to set them a 422. Two writers, both
  ledgered as `registry.attested`: `POST /agents/{id}/attest` (body
  `{attested_by}`, stripped; blank/whitespace ⇒ 422; unknown ⇒ 404), and the
  CLI `registry attest <id> --by NAME`, which writes SQLite directly and
  therefore appends the event itself — exit 3 when a configured ledger
  refuses, and a printed notice when `FIELD_LEDGER_URL` is unset. Nothing
  else moves the field: `store.update()`'s UPDATE omits the column.
  lifecycle-manager's re-attestation basis is this field, and it is the only
  field that clears a `lifecycle.reattestation_due` escalation — which is why
  an unledgered write is treated as a failure rather than a convenience.
- Forward-only SQLite migration in `RegistryStore.__init__`
  (`PRAGMA table_info` → `ALTER TABLE ADD COLUMN`), because the shipped
  schema is `CREATE TABLE IF NOT EXISTS` and the estate databases are
  persisted files; the positional `INSERT` is now named-column.
- `attested_by` is a recorded string, not an authenticated identity.

**Explicit non-goals (v0.1)**
- No DELETE — agents are retired, never erased (audit trail).
- No manifest validation on registration (field-core owns that).
- No ledger emission on registry writes (Phase 2).
- No connectors beyond n8n-export + CSV (no live n8n API, no cloud IAM).
- No LLM anywhere; the scanner is labeled heuristic.
