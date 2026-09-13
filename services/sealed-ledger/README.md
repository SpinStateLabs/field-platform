# sealed-ledger

Append-only, sha-256 hash-chained event ledger. FIELD letter **L** (Ledger).
Exec owner: **CFO / audit**.

Every governance-relevant event on the platform — actions, blocks,
escalations, token mints and revocations, kills, spends — lands here as a
chained record. `verify` walks the chain and reports the **first break**.

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/events` | POST | Append an event (`event_type`, `agent_id`, `payload`) |
| `/events` | GET | Filtered read: `agent_id`, `event_type`, `since`, `until`, `limit`. `since`/`until` are inclusive ISO 8601 instants (compared as datetimes; 422 if unparseable) |
| `/verify` | GET | Walk the chain; report first break index + reason |
| `/export` | POST | Auditor export bundle written to `out_dir/<stamp>/` **on the ledger host** (query: `out_dir`, `since`, `until`, `agent_id`, `event_type`). Always unsigned (`signed: false`) |
| `/health` | GET | Liveness + event count + head hash (sentinel uses this) |

## CLI

```
ledger append <event_type> [--payload JSON] [--agent-id ID] [--path FILE]
ledger verify [--path FILE] [--anchors FILE [--pubkey PEM]]   # exit 1 on first break
ledger anchor --anchors FILE [--key PEM] [--path FILE]
ledger export [--out-dir DIR] [--path FILE] [--since ISO] [--until ISO]
              [--agent-id ID] [--event-type TYPE] [--sign-key PEM]
ledger verify-export BUNDLE_DIR [--pubkey PEM]   # exit 1 on failure, naming the first failing index when it has one
ledger serve [--host H] [--port 8002]
```

## Auditor export bundle

`ledger export` and `POST /export` write a new directory `OUT_DIR/<stamp>/`
every time (an existing bundle is never overwritten). The ledger file is read
once; the selection, the spine, `head_hash` and the verification all come from
that one read. Filters are the same predicate as `GET /events`.

| File | Contents |
|---|---|
| `events.jsonl` | The exported events, one pure `LedgerEvent` JSON object per line (no added keys) |
| `summary.json` | `event_count`, `event_types`, `agents`, `first_ts`/`last_ts`, `indices` (the global chain index of each exported line), `first_index`/`last_index`/`head_index`, `head_hash`, `verification` of the FULL live chain at export time, `signed` |
| `chain_proof.json` | `first_index`, `last_index`, `head_index`, `first_prev_hash`, `head_hash`, `verification`, `filters`, `spine` = `[{index, event_id, prev_hash, hash}]` for EVERY chain event from `first_index` to `head_index`, exported or not |
| `signature.json` | `signed: false`; or, with `ledger export --sign-key`, an Ed25519 signature over the canonical JSON of `{"summary": <summary.json>, "chain_proof": <chain_proof.json>}` plus `key_fingerprint` (sha-256 of the raw 32-byte public key) |

`ledger verify-export BUNDLE_DIR [--pubkey PEM]` recomputes every exported
event's hash and requires it to equal the spine's hash at that event's index,
walks the spine links from `first_prev_hash` to `head_hash`, recomputes the
counts, and checks the signature. Exit 1 on any failure, naming the first
failing index when the failure has one (a wrong key or a missing file has
none). An unsigned bundle checked with `--pubkey` fails, including a 0-byte
`--pubkey` file. It also enforces:

- **No recorded filter means every event.** A bundle whose `filters` are all
  null must export every index `0..head_index`, and `first_prev_hash` must be
  the genesis hash whenever `first_index` is 0. Deleting an event from an
  unfiltered bundle fails naming the first missing index, even when the
  indices and counts in `summary.json` and `chain_proof.json` were re-edited to
  match. A deletion that ALSO rewrites `head_index`/`head_hash` (and re-links
  the chain) is internally consistent again: only a valid signature under
  `--pubkey`, or comparing the printed `head_hash` with a pinned or anchored
  head, catches it. It prints
  `filters: none — every index 0..N is exported (verified)`; a filtered bundle
  prints its filters and `completeness of a filtered export is not provable`.
- **What is shown is what is verified.** Every JSON file and every
  `events.jsonl` line is parsed with duplicate keys refused, so a decoy key
  that one reader (`grep`, a human) sees first and another (`json.loads`,
  `JSON.parse`, `ConvertFrom-Json`) overrides fails verification instead of
  passing under a genuine signature. `events.jsonl` is split on `\n` only, as
  the ledger itself reads it, so a genuine payload holding U+2028, U+2029 or
  NEL verifies.

Compare the `head_hash` that `verify-export` **prints** with a pin or anchor,
never one read out of the files by hand.

What a bundle proves, and what it does not:

| Bundle | `verify-export` prints | Proves | Does not prove |
|---|---|---|---|
| Unsigned (every served `/export`), or signed but checked without `--pubkey` | `spine unverified (unsigned)` / `spine unverified (signed, but no --pubkey given …)` | **Internal consistency only**: the four files agree with each other, and a bundle with no recorded filter exports every index `0..head_index` | Anything about the ledger. Whoever holds the files can replace an exported event and re-link the hash-only gap after it, or claim another `head_hash` (`test_unsigned_filtered_bundle_cannot_detect_a_relinked_forgery`, `test_unsigned_bundle_head_can_be_forged_but_not_under_signature`) |
| Signed, checked with the signer's public key | `signature valid (key <fingerprint>)` | The spine, head and counts are the ones the key holder attested; each exported event is bound to them by its hash | That the key holder told the truth; that a filtered export is complete |
| Either, plus the printed `head_hash` compared with an anchor held off-box (taken at `chain_length = head_index + 1`) | `contiguous: …` or `filtered: …` | **Independent proof** for a contiguous bundle (every index `first_index..head_index` exported): each link to the anchored head was recomputed from event content, so those events are the ledger's. `filters: none` plus `contiguous: every link from index 0` is the whole chain up to the anchor | For a filtered bundle, only the head: its gaps are hash-only entries nobody can recompute |

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Every event is hash-linked to its predecessor | **Enforced in code** | `store.append` seals under a lock; genesis links to 64 zeros |
| A naive on-disk mutation or deletion of a mid-chain record is detectable | **Enforced in code** | `verify` recomputes every hash + link; adversarial tests mutate and delete mid-chain records on disk and prove detection. NOT covered here: deleting the tail, or mutating a record and re-hashing and re-linking every record after it, passes plain `verify` — only the anchor row below catches those |
| Appends are durable when acknowledged | **Enforced in code** | flush + fsync before returning |
| Auditor export is re-verifiable offline (hashes + spine); Ed25519-signed only via `ledger export --sign-key` — the served `/export` is unsigned (`signed: false`) | **Enforced in code** | `verify-export` recomputes every exported hash against the spine, walks the spine to `head_hash`, recomputes counts, checks the signature. `tests/test_export_bundle.py`: one edited event ⇒ exit 1 naming its index; a deleted line fails; a filtered (agent_id) export of an interleaved two-agent chain verifies via the spine and prints "spine unverified" when unsigned; `summary.json` tampered on a signed bundle fails; wrong key fails; unsigned + `--pubkey` fails; the served route writes `signed: false` |
| A bundle that records no filter exports every index `0..head_index` (deleting an event fails when the indices and counts are re-edited but `head_index`/`head_hash` are not), and no bundle file or event line may repeat a key | **Enforced in code** | The recorded filters and the head of an UNSIGNED bundle can themselves be edited: a deletion that also rewrites `head_index`/`head_hash` verifies, so an auditor relying on completeness must see `filters: none` in the output AND a printed `head_hash` equal to a pinned/anchored head (or a valid signature under `--pubkey`). `summary.json` accepts unknown keys, so an extra, differently-named key is not refused. `tests/test_export_bundle.py`: middle, tail, head deletion and an emptied bundle each fail with `summary.json`/`chain_proof.json` re-edited (`test_deleting_a_middle_event_from_an_unfiltered_bundle_fails_even_with_summary_reedited`, `test_dropping_the_tail_…`, `test_dropping_the_first_events_…`, `test_emptying_an_unfiltered_bundle_fails`); a non-genesis start at index 0 fails; duplicate-key decoys in an event line (signed, genuine key) and in each JSON file fail; genuine U+2028/U+2029/NEL payloads verify |
| `verify-export` never presents an unsigned bundle as proof of what the ledger holds | **Enforced in code** | unsigned (or no `--pubkey`) prints "spine unverified"; unsigned + `--pubkey` exits 1; `test_unsigned_filtered_bundle_cannot_detect_a_relinked_forgery` pins the limit: an unsigned bundle is internal consistency only, and independent proof = `head_hash` compared with an off-box anchor (covering the exported events only for a contiguous bundle); a `--until` window that ends before head is reported `filtered:`, never `contiguous:` (`test_a_windowed_export_that_ends_before_head_is_not_contiguous`) |
| A filtered export is complete (every matching event included) | **Declared only** | the spine carries only hashes for events it does not export, so a verifier cannot re-run the filter |
| Time windows are exact (ISO 8601 instants, both bounds inclusive) | **Enforced in code** | `datetime.fromisoformat`, naive ⇒ UTC (`sealed_ledger/filters.py`); `tests/test_time_filters.py`: `Z` vs `+00:00`, mixed offsets, exact-bound inclusivity, garbage ⇒ 422 |
| Nobody can rewrite history *undetectably* | **Declared only** | plain `verify` is blind to a self-consistent full rewrite (`test_adversarial_full_history_rewrite_beats_verify_but_not_anchors` asserts it passes); detection needs the anchor row below with the anchor file held off-box, which is deployment responsibility |
| Full-history rewrites are detectable against anchors | **Enforced in code** | `ledger anchor` pins (length, head hash); `verify --anchors` demands the chain still contain them — adversarial test proves a self-consistent forgery passes plain verify but fails the anchor check. Signed anchors (Ed25519) make the anchor file itself tamper-evident |
| Nobody can rewrite history *at all* | **Declared only** | filesystem write access defeats append-only-ness; WORM storage + off-box (or public-chain) anchor placement is deployment responsibility |
| Signatures / authorship of events | **Declared only** | v0.1 events are unsigned; any writer with API access is trusted. An export's `signature.json` signs the bundle (summary + chain_proof), not the events; per-event signatures are F2 |
| Retention periods in manifests | **Declared only** | nothing deletes or holds data on a schedule yet |

## LIMITS

- Single-writer per file: the append lock belongs to one `LedgerStore`
  instance, so two instances on the same file (even in one process) fork the
  chain. Run one instance per ledger file (the docker-compose demo does).
- Chain is linear sha-256, not Merkle. A full-chain forgery is caught by
  `verify --anchors` — but only if the anchor file lives where the attacker
  can't reach it. Ship it off-box on every `ledger anchor` run, or publish
  each anchor record to a public blockchain (OpenTimestamps-style — the
  record is one small JSON object). An anchor on the same disk as the
  ledger protects against nothing.
- Reads scan the file (no index). Fine for demo scale; SQLite index is a
  later milestone.
- API authn is one optional shared secret (`FIELD_SHARED_SECRET` →
  `x-field-auth`; `/health` stays open). Every holder is equal: there is no
  read-only auditor role, and any holder can call `/export`.
- **The served export writes server-side.** `POST /export` writes the bundle
  to a directory on the ledger host (`out_dir`, default `<ledger dir>/exports/`)
  and returns only the summary. A remote auditor cannot fetch the bundle
  without estate access (`docker cp` + `scp` on the GB10, `fly ssh sftp get`
  on Fly). `out_dir` is not constrained: it is any path the ledger process can
  write.
- **An unsigned bundle proves internal consistency only.** Every served
  export is unsigned. Independent proof means comparing `head_hash` with an
  anchor held off-box, and that covers the exported events only for a
  contiguous (unfiltered-to-head) bundle. A signed bundle moves trust to the
  signer's key: `--sign-key` reads a PEM on the machine running the CLI (key
  custody is the operator's), and `key_fingerprint` in `signature.json` names
  the key without making it trusted — the verifier must get the signer's
  public key out-of-band.
- Export reads the ledger without the append lock, like every reader; an
  append that lands after the read is not in the bundle. `head_index` and
  `head_hash` describe the chain as read (not the in-memory cached head).
- The spine lists every event from the first exported one to the head, so a
  filtered export whose first match is old carries a long spine.
- Time bounds: a naive timestamp or a date alone is UTC, and a date alone is
  00:00:00 that day, so `until=2026-09-30` excludes the rest of 30 September.
  An unparseable bound is refused (422 / exit 2). Before C1 the comparison
  was lexical: a garbage `since` silently returned `[]`, and a garbage `until`
  silently returned the WHOLE unfiltered history (a widened window). Replay or
  attestation windows computed before C1 with a malformed `until` may have
  covered more than they said. A stored event whose `ts` is not ISO 8601 makes a time-filtered
  read fail (HTTP 500) rather than being silently kept or dropped.
