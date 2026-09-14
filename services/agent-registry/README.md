# agent-registry

Agent identity records + shadow-agent discovery. FIELD letter **I**
(Identity). Exec owner: **CIO**.

If it isn't in the registry, the platform treats it as ungoverned. The
discovery scanner turns artifacts every IT org already has — an n8n
workflow export, a service-account inventory, an API-key / credential
inventory and any text you can paste — into a review queue of
"unregistered agent candidates" and redacted credential-shaped strings.

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/agents` | POST | Register an agent (id, name, human owner, domain, manifest ref). A SET `manifest_ref` that does not resolve ⇒ 422 `{error, manifest_ref, reason: missing\|invalid, manifest_dir, hint}` (v1.2 D3b) |
| `/agents` | GET | List (filter by `status`, `domain`) |
| `/agents/{id}` | GET / PATCH | Read / update (incl. `status`: active·killed·retired) |
| `/agents/{id}/attest` | POST | Record a human re-attestation: body `{attested_by}` (stripped; blank ⇒ 422, unknown agent ⇒ 404) |
| `/discover` | POST | Scan `n8n_export` JSON, `accounts_csv`, `api_keys_csv` (`key_name,owner,service,created,last_used[,last_used_by]`) and/or `secrets_text`; `principals_csv` (owners.csv) widens the known owners. Unknown or wrong-typed field, no scannable input, a malformed or unreadable CSV, a key row with a blank `key_name`, a `principals_csv` with no `owner`/`name` column, or any input over 1 MiB ⇒ 422 |
| `/health` | GET | Liveness + agent count |

## CLI

```
registry add <agent-id> --name N --owner O [--domain D] [--manifest-ref R]   # exit 2: R does not resolve
registry list [--status S] [--domain D]
registry attest <agent-id> --by NAME                            # sets attested_at/attested_by
registry scan [--n8n export.json] [--accounts accounts.csv] \
              [--api-keys keys.csv] [--secrets-text dump.txt] \
              [--principals owners.csv] [--very-broad]
              # exit 3 candidates or credential-shaped strings; 2 no/malformed/oversized input
registry serve [--port 8001]
```

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| One record per agent id; well-formed slugs; human owner required | **Enforced in code** | Pydantic + SQLite primary key. `name` and `owner` are `min_length=1` on create AND on PATCH: an empty value is a 422 at the request model, the row unchanged and no ledger note (`tests/test_registry_update_validation.py`). Non-empty only: a whitespace-only value is accepted |
| Status transitions persist and are queryable (kill-switch reads these) | **Enforced in code** | SQLite store. A PATCH writes only the fields it carries, reading and writing in one lock hold and one `BEGIN IMMEDIATE` transaction, so a concurrent PATCH of another field cannot write an old `status` back over a kill. Two connections to the same file are covered too. A kill raced by edits ledgers exactly one `registry.status_changed` (`tests/test_registry_update_atomicity.py`) |
| AI workflows/accounts in scanned artifacts surface unless registered | **Enforced in code** | deterministic node-type + name-pattern scanner (see adversarial test: renaming a workflow doesn't hide it) |
| File-based credential-inventory and secrets-text scan (labeled heuristic) | **Enforced in code** | `scan_api_keys`: blank owner ⇒ `unowned API key`; owner not a registered agent's owner (case-insensitive exact after strip — lifecycle-manager's roster rule) ⇒ `owner is not a registered agent's owner`, EVEN when the key is named after a registered agent; `last_used_by` not an owner, agent id or agent name ⇒ `last used by unknown principal`; a malformed inventory (missing column, extra field, unquoted `Name, Org`, a row with values but a blank `key_name`, a CSV the csv module cannot read such as a field over its 131072-character limit) is refused by name and line — 422 / exit 2, never a 500, never a report that silently scanned less — and so is a `principals_csv` with neither an `owner` nor a `name` column. `scan_secrets_text`: ordered, boundary-checked `KEY_PATTERNS`, each labeled `low`/`moderate`/`broad`/`generic`, a span counted once (`sk-ant-` never also `sk-`); the `very-broad` assignment pattern is OFF unless `--very-broad`. Every hit is redacted by the model (`SecretHit` keeps prefix 7 + `…` + last 4, never more than half, + a sha256 fingerprint), and every string any candidate echoes passes through the same redaction (except a broad `sk-`/`sk-proj-` key glued directly onto a letter or digit — LIMITS). `DiscoverRequest` is `extra='forbid'`; a request-validation 422 on any route returns each error's `type`, `loc` and `msg` only, never its `input` or `ctx`, with `loc` and `msg` redacted, so a typo'd or wrong-typed field carrying a key is not echoed; each input capped at 1 MiB (`tests/test_d3_credential_scan.py`, `tests/test_d3_scan_hardening.py`) |
| The registry knows about *all* agents in the org | **Declared only** | discovery covers only the artifacts you feed it; an agent, key or credential outside the n8n export, the account inventory, the key inventory and the text you paste is invisible |
| A SET `manifest_ref` resolves to a valid manifest when the agent is registered | **Enforced in code** | v1.2 D3b. `POST /agents` (422) and `registry add` (exit 2) resolve it with field-core's shared resolver — the one the sentinel, delegation, kill-switch and ledger retention read with — against `FIELD_MANIFEST_DIR` in the registering process: a missing file and a file that fails `field validate`'s checks are both refused, before the duplicate check and before any write or ledger event. An unset (absent, `null`, `""`) ref registers as before (`tests/test_d3b_manifest_ref_resolves.py`) |
| `manifest_ref` keeps pointing at a valid manifest after registration | **Declared only** | `PATCH /agents/{id}` does not re-check it (so lifecycle `provision`'s 409 ⇒ PATCH path can set an unresolvable ref on an existing agent), a manifest can be removed or broken after it was registered, and records registered before D3b were never checked. The readers' `missing`/`invalid` handling and `ledger retention check` / the lifecycle retention finding are what see those |
| `attested_at` moves only on an explicit attestation — no PATCH can forge or reset it | **Enforced in code** | `AgentUpdate` has neither field and is `extra='forbid'`: a PATCH carrying `attested_by`/`attested_at` is a 422, and a kill/revive cycle leaves `attested_at` untouched (adversarial tests) |
| `attested_by` is the human who attested | **Declared only** | a recorded string, not an authenticated identity — the registry takes the caller's word for the name |
| `owner` is a real, current human | **Declared only** | roster reconciliation is lifecycle-manager's job (Phase 4) |

## LIMITS

- **The credential scans read files you export — there is no live IAM,
  cloud or secret-manager connector.** Export the key inventory yourself
  (`key_name,owner,service,created,last_used[,last_used_by]`; the spec's
  `last_used` is a timestamp, so "last used by an unknown principal" needs the
  optional `last_used_by` column). A key that is not in the file is not seen.
- **Owner matching is exact strings, not identity.** IAM exports carry emails
  (`growth@example.test`) where registry owners are names (`Controller, Spin
  State Labs`): expect false positives. `--principals owners.csv` /
  `principals_csv` (lifecycle-manager's roster format, `owner[,aliases]`)
  widens the known owners and principals; it resolves nothing.
- **Pattern breadth is labeled because some patterns are wrong a lot.**
  `openai-style-sk` (`sk-`, `sk-proj-`) is **broad** — many non-OpenAI strings
  start that way; `jwt` is **generic** (token-shaped, not whose); `huggingface`
  (`hf_`) is **moderate**; the provider-prefixed patterns (`sk-ant-`, `AIza`,
  `AKIA`/`ASIA`, `gh[pousr]_`, `xox[baprs]-`, `sk_live_`/`sk_test_`, `ya29.`)
  are **low**. The **very-broad** `api_key|secret|token = value` pattern
  ships OFF (`--very-broad` on the CLI; not exposed on `/discover`). A
  credential format none of these names is not found.
- **Redaction shows a little.** A hit keeps its first 7 and last 4 characters
  (never more than half of the value) and a 16-hex sha256 fingerprint for
  correlation. The fingerprint of a low-entropy value (a very-broad
  `token=password123`) is guessable by brute force. Strings a candidate
  echoes are redacted more aggressively than scans report, with the
  very-broad pattern on. A provider-prefixed key is redacted wherever it sits,
  including glued onto letters or digits (`prod<sk-ant-key>`). An ordinary
  identifier that happens to contain such a prefix plus enough characters gets
  redacted too, which in an echo is the safe error. The **broad** `sk-` /
  `sk-proj-` pattern is redacted glued on with `-` or `_` (`wf-<key>`), but
  **not glued directly onto a letter or digit** (`prodsk-proj-…` is echoed as
  is): `task-…`, `desk-…` and `risk-…` identifiers end in `sk-`, so that
  boundary stays (`test_limit_a_broad_sk_key_glued_onto_a_letter_is_not_redacted`).
  A validation error from either report model never quotes its input
  (`hide_input_in_errors`), nor does a request-validation 422.
- **The 1 MiB cap is per field, after the request body is parsed.** It stops a
  scan of an oversized input; it does not stop an oversized body reaching the
  process — that is the fronting proxy's job.
- **D3b resolves in the registering process.** `POST /agents` resolves against
  the registry container's `FIELD_MANIFEST_DIR` (`/data/manifests` on both
  estates, where every reader resolves too); `registry add` resolves against
  the operator shell's, so an estate path (`/data/manifests/x.yaml`) run from a
  laptop is refused. URL-form refs were never resolvable by any reader and are
  now refused at register. Install the manifest (`manifests-admin install`)
  BEFORE registering an agent that names it.

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
