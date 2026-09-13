# SPEC — lifecycle-manager

**Purpose:** Scheduled sweep over agent-registry + delegation-authority:
report authorities expiring within a horizon, agents due for
re-attestation, and orphaned agents whose owner is absent from the human
roster (owners.csv). Every finding is a ledger escalation; orphan auto-kill
exists but only behind an explicit flag.

**Exec owners:** CIO / CHRO.

**FIELD letters:** I (identity/ownership) + D (delegation hygiene).

**v0.1 scope**
- `lifecycle sweep` CLI (exit 3 on findings) with `--roster`,
  `--expiry-days` (30), `--reattest-days` (90), `--auto-kill-orphans`
  (default OFF), `--operator`, `--markdown`.
- `lifecycle serve` (:8012): `GET /health`, `POST /sweep`, `GET /findings`.
  Roster from the request body or `FIELD_LIFECYCLE_ROSTER`; neither ⇒ 503.
  Optional in-process scheduler `--every` / `FIELD_LIFECYCLE_EVERY` (0 = off),
  first tick after the interval, roster-less ticks recorded as skips, a
  raising tick never stops the loop, and auto-kill unreachable from it.
- Deterministic engine: token expiry window, re-attestation staleness,
  case-insensitive roster membership.
- Ledger events: `lifecycle.expiring_authority | reattestation_due | orphan`;
  auto-kills go through kill-switch with a sweep-attributed reason.
- Idempotent: re-sweeps re-report, never double-kill.
- Adversarial test: auto-kill without the flag must not happen.

**v1.2 additions (B4)**
- Re-attestation basis is the registry record's `attested_at`, falling back
  to `created_at`, and NEVER its edit timestamp (a grep-guard test pins that
  the engine module never reads one). `ReattestationDue` gains `basis` and
  `attested_by`; the `lifecycle.reattestation_due` payload gains the same two
  keys and keeps every existing one, so downstream counters do not break.
- `lifecycle provision --manifest --owner --domain --grantor --ttl-days
  [--name] [--manifest-ref] [--out]` => `engine.provision(...)` with injected
  clients: `validate_manifest_file` (INVALID => exit 1, zero side effects) ->
  register (409 => PATCH owner/manifest_ref, reported as `updated`) -> cap via
  `SpendCapConfig.from_manifest` (one cents rule, `round`) -> mint (the
  delegation service's 403/422/503 pass through verbatim). `ProvisionReport`
  carries `token_id` and a per-step list; a mid-sequence failure is reported
  step by step, never pretended atomic. `spend-governor` is therefore a
  RUNTIME dependency of this package (precedent: field-agent ->
  conformance-sentinel), and both Docker images already install
  lifecycle-manager after spend-governor.
- `lifecycle decommission <agent> --by NAME --reason [--out]`:
  `registry.get_agent` (unknown => exit 1, nothing created) -> already
  `retired` => ledger `lifecycle.decommissioned{noop: true}` and exit 0 with
  NO kill -> revoke every non-revoked token (a 502 from the ledger-first
  revoke is reported and the run continues act-first, exiting non-zero at the
  end) -> kill via the kill-switch ONLY when the status is `active` ->
  registry `retired` -> ledger `lifecycle.decommissioned{by, reason,
  tokens_revoked, killed}`.
- Cross-package: the kill-switch answers 409 to `/kill` and `/revive` for a
  retired agent and skips them in `/kill/domain`; the ops-console hides the
  revive button for them.
- `tools/provision_ssl_agents.py` is a thin wrapper over `provision`.

**v1.2 additions (A1b — owners roster aliases)**
- `owners.csv` gains an OPTIONAL `aliases` column: `;`-separated strings the
  registry records for the same human as `owner`. An agent whose registry
  owner equals the owner or any alias (case-insensitive, exact after strip)
  is not an orphan. Blank alias entries are dropped; a row with no owner is
  dropped with its aliases.
- `engine.parse_roster_entries(csv) -> list[RosterEntry(owner, aliases)]`;
  `engine.parse_roster(csv) -> set[str]` returns every owner and alias
  string, lower-cased (unchanged output for a roster without the column).
- `SweepReport.roster_size` counts humans (distinct owners), never alias
  strings; the orphan reason's `(N entries)` uses the same number.
- A row with more fields than the header (an unquoted comma) raises
  `ValueError` naming the line instead of the former `AttributeError`. So
  does a data row where a value starts with whitespace (space, TAB, NBSP,
  U+3000, ...) right after an unquoted comma (`Don Hagell, Spin State Labs`
  under a two-column header, which has exactly the header's field count). An
  unquoted comma with no following whitespace and no more fields than the
  header cannot be told from owner + alias and is not detected.
- Non-goal restated: an alias is declared by whoever writes the CSV; nothing
  verifies that the strings name one person.

**Explicit non-goals (v0.1)**
- No external scheduler: `--every` is in-process and unpersisted; Task
  Scheduler/cron remains the durable cadence.
- No identity resolution on owners (exact-string roster match).
- No HTTP route can arm auto-kill without an explicit body flag.
- No re-attestation workflow beyond recording it: `registry attest` writes a
  name and a timestamp; nothing verifies that a review happened.
- Neither transition is atomic and neither rolls back; the report says
  where it stopped.
