# SPEC — sealed-ledger

**Purpose:** The platform's immutable audit trail. Append-only event API where
every event is sha-256-chained to the previous one; verification walks the
chain and reports the first break; auditor export produces a bundle an auditor
can re-verify offline.

**Exec owner:** CFO / audit.

**FIELD letter:** L — Ledger.

**v0.1 scope**
- JSONL store; append serialized under a lock; flush+fsync on append; head
  hash recovered on restart.
- FastAPI: POST/GET `/events`, GET `/verify`, POST `/export`, GET `/health`.
- CLI: `ledger append | verify | anchor | export | verify-export | serve`.
- Tamper tests: mutate a middle record on disk → detection at that index;
  delete a middle record → link break at that index.
- Anchors: `ledger anchor` pins (length, head hash), optionally Ed25519-signed;
  `verify --anchors` catches a self-consistent full rewrite.
- `since`/`until` filters compare ISO 8601 instants (`datetime.fromisoformat`,
  naive ⇒ UTC), both bounds inclusive; an unparseable bound is refused (422).
- C1 auditor export: `POST /export` and `ledger export` take `since`, `until`,
  `agent_id`, `event_type` and write `out_dir/<stamp>/` with `events.jsonl`
  (pure `LedgerEvent` lines), `summary.json` (+ `indices`, `first_index`,
  `last_index`, `head_index`), `chain_proof.json` (`first_prev_hash`,
  `head_hash`, verification of the full live chain, filters, and a hash spine
  `[{index, event_id, prev_hash, hash}]` from `first_index` to `head_index`)
  and `signature.json` (Ed25519 over canonical summary + chain_proof with
  `key_fingerprint`, only via `ledger export --sign-key`; the served route
  writes `signed: false`). `ledger verify-export <dir> [--pubkey]` recomputes
  the exported hashes, walks the spine to `head_hash`, checks counts and the
  signature, and exits 1 on failure (naming the first failing index when the
  failure has one); unsigned bundles report "spine unverified (unsigned)".
  A bundle with no recorded filter must export every index `0..head_index`
  (a deleted event fails naming the first missing index), `first_index` 0
  must start at the genesis hash, duplicate JSON keys are refused in every
  file and line, and `events.jsonl` is split on `\n` only.
- C2 core, retention by rotation (build spec `C2-BUILD-SPEC.md`, design A +
  grafts G1–G7): the path given is always the open segment; `rotate` renames
  it to `<stem>-<n><suffix>` and installs a new open segment whose first event
  is a signed, hash-chained `ledger.segment.rotated` (operator, reason, closed
  range and head, anchor `{anchored_at, chain_length, head_hash, segment}`).
  Append-only journal `<stem>.segments.journal` (`field-ledger-segments/1`:
  `rotate-intent` → `rotate-commit`/`rotate-abort`; `archive` parsed and
  honoured by readers, written by retention apply). Step order intent → tmp →
  rename → rename → commit, with inert `FIELD_LEDGER_CRASH_AT` hooks at each
  step; reconcile only under the writer locks (next write, `reconcile()`, or
  served startup when `needs_reconcile()`). Writers: in-process RLock + a
  cross-process lock file `.<name>.lock`. Readers: lock-free snapshot validated
  against the journal bytes and the watched paths, one pre-validation handle
  (the open segment), share-delete opens on Windows, a heavy-read gate
  (`FIELD_LEDGER_READ_CONCURRENCY`, default 1; served reads queue on a lane
  that width, `/health` and appends have their own). `/health` from a cache
  (`event_count` global, `earliest_live_index`, `earliest_live_ts`). `verify`
  walks every live segment, names `segment <n>` and the global index, and
  cross-checks each journal entry against the next rotation event; a journal
  line missing a field its op needs, or a segment that does not start from the
  previous head, is an invalid line (a break reported after the walk); EVERY
  `archive` record needs its own evidence: its file while that file is still
  in the ledger dir, else a hash-chained `ledger.retention.applied` event in
  the live chain whose `archive_evidence` names that segment with the
  journaled sha-256, else its archive copy (which must verify);
  `ChainVerification` gains `segments`, `archived_segments`,
  `verified_events`, `break_segment` (omitted on a single-file chain). Anchors
  resolve global positions from one snapshot (`hash_at` → hash | "archived" |
  None; an archived position is an explicit failure). Export bundles use
  global indices (`start_index`), and `verify-export` accepts an archived
  prefix on a segmented ledger. `POST /rotate {operator, reason}` with the key
  at `FIELD_LEDGER_ANCHOR_KEY` read per request (unset/unreadable/unusable ⇒
  503). CLI: `ledger verify --path` dispatch (open segment / live closed
  segment / `--genesis` / single file), `BUSY` exit 4, `ledger rotate`
  (served via `FIELD_LEDGER_URL`, else `--offline`).
- C2 retention operations (build spec §5.1-§5.7): `archive_closed_segments`
  / `POST /retention/apply` / `ledger retention apply --days N --operator`
  (archive dir under `FIELD_DATA_DIR` unless `--allow-external`, never inside
  the live ledger dir, same filesystem; per segment verify against the
  journal and the successor's rotation event → sidecar
  `<file>.segment.json` → journal `archive` op under both writer locks →
  `os.rename` outside the locks, never overwriting; pending moves completed
  by the next apply; one `ledger.retention.applied` event per run that did
  something, also when the run is refused part-way (with `error`); refused
  when live verify breaks, and under a legal hold, re-checked before the
  sidecar and under the lock; crash
  hooks `archive.sidecar_written`, `archive.op_torn`, `archive.committed`,
  `archive.moved`). `verify_segment_file` and the `ledger verify --path`
  sidecar dispatch (with `--pubkey`, the signed rotation anchor).
  Legal hold `legal_hold.json` via `place_hold` / `release_hold`, `POST
  /hold`, `POST /hold/release`, `GET /hold`, `ledger hold place|release`
  (blank names refused; file then `ledger.legal_hold.placed`; event
  `ledger.legal_hold.released` then unlink; crash hooks `hold.file_written`,
  `hold.event_first`). Retention check `GET /retention/check` / `ledger
  retention check` (`sealed_ledger/retention.py`: `FIELD_LEDGER_RETENTION_DAYS`
  vs every registered manifest's `ledger.retention_days` through the B0
  resolver; no-ref agents skipped and counted; exit 3 unless `ok`;
  `create_app(store=…)` without a registry = `unavailable`, no network).
  The hold and retention verbs delegate to the served routes when
  `FIELD_LEDGER_URL` is set, else refuse unless `--offline`.

**Explicit non-goals (v0.1)**
- No Merkle proofs and no per-event signatures (the export signs a bundle,
  anchors sign an anchor record; events themselves are unsigned until F2).
- No proof that a filtered export is complete, and no proof of ledger
  contents from an unsigned bundle (internal consistency only).
- No per-agent retention and no deletion: retention is estate-level (one
  chain), `/retention/check` reports and never enforces, and retention apply
  moves closed segments to an archive directory on the same filesystem. What
  happens to archived files afterwards is the operator's.
- No syscall-level crash sweep of retention apply (named steps only), no
  test on Linux or at 100k events for it, and no tamper-evidence for an
  unsigned sidecar or the hold marker.
- No protection for pre-C2 readers or writers of a rotated ledger, no power
  loss durability claim, and no rotation on Windows while a foreign process
  holds the open segment with a plain handle (503, nothing renamed).
- API authn is a single optional shared secret; no reader/auditor roles.
- No way to fetch a served export over the API: the bundle stays on the
  ledger host.
- No storage backend other than local JSONL.
