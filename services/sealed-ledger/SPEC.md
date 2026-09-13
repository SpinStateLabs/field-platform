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

**Explicit non-goals (v0.1)**
- No Merkle proofs and no per-event signatures (the export signs a bundle,
  anchors sign an anchor record; events themselves are unsigned until F2).
- No proof that a filtered export is complete, and no proof of ledger
  contents from an unsigned bundle (internal consistency only).
- No retention enforcement (manifest `retention_days` is declared only).
- API authn is a single optional shared secret; no reader/auditor roles.
- No way to fetch a served export over the API: the bundle stays on the
  ledger host.
- No storage backend other than local JSONL.
