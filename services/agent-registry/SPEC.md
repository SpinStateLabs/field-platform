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

**v1.2 additions (D3, D3b)**
- `discover.scan_api_keys(csv_text, registered, known_principals=None) ->
  (candidates, scanned)` over `key_name,owner,service,created,last_used
  [,last_used_by]` (header required, extras ignored, a malformed file refused
  by name). Distinct reasons: `unowned API key`; `owner is not a registered
  agent's owner` (case-insensitive exact, lifecycle-manager's roster rule —
  applies even when `key_name` matches a registered agent); `last used by
  unknown principal`. `parse_principals(owners.csv)` widens both known sets.
- `discover.scan_secrets_text(text, include_very_broad=False)` over the
  ordered, boundary-checked, breadth-labeled `redaction.KEY_PATTERNS`; a span
  is counted once. Hits are `models.SecretHit`, which takes the raw value and
  keeps only prefix 7 + last 4 (never more than half) + a sha256 fingerprint.
  `ShadowCandidate` redacts every echoed string the same way.
- `DiscoverRequest` gains `api_keys_csv`, `secrets_text`, `principals_csv`
  and `extra='forbid'`; each input is capped at 1 MiB (`ScanInputError` ⇒
  422, CLI exit 2). `ScanInputError`, never a 500 or an exit-0 report, also
  covers: a key row with values but a blank `key_name`; a CSV the csv module
  cannot read (`csv.Error`, e.g. a field over 131072 characters, in any of
  `api_keys_csv`, `accounts_csv` or `principals_csv`), named by line; and a
  `principals_csv` with neither an `owner` nor a `name` column. Every
  request-validation 422 returns `type`/`loc`/`msg` only (no `input`, no
  `ctx`; `loc` and `msg` redacted). `DiscoveryReport` gains `scanned_api_keys`,
  `scanned_secret_hits`, `secret_hits` (defaults keep every older report).
- CLI `registry scan --api-keys FILE [--secrets-text FILE] [--principals FILE]
  [--very-broad]`; exit 3 on candidates or hits.
- D3b: `POST /agents` refuses a SET `manifest_ref` that field-core's shared
  resolver (`resolve_manifest_detail`, `FIELD_MANIFEST_DIR`) reports
  `missing` or `invalid` — 422, checked before the duplicate check and before
  any write or ledger event; `registry add` exits 2 on the same rule. PATCH is
  not checked (README LIMITS).

**Explicit non-goals (v0.1)**
- No DELETE — agents are retired, never erased (audit trail).
- No manifest validation of its own: since v1.2 D3b registration resolves a
  set `manifest_ref` through field-core's shared resolver (field-core owns the
  validation rules); PATCH does not.
- ~~No ledger emission on registry writes~~ — stale since Phase 2: HTTP
  writes append `registry.registered` / `registry.status_changed` /
  `registry.updated` / `registry.attested` (best-effort); the CLI ledgers only
  `attest`.
- No connectors beyond n8n-export + CSV + pasted text (no live n8n API, no
  cloud IAM, no secret manager — the credential inventory is a file you export).
- No LLM anywhere; the scanners are labeled heuristic.
