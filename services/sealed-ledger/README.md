# sealed-ledger

Append-only, sha-256 hash-chained event ledger. FIELD letter **L** (Ledger).
Exec owner: **CFO / audit**.

Every governance-relevant event on the platform — actions, blocks,
escalations, token mints and revocations, kills, spends — lands here as a
chained record. `verify` walks the chain and reports the **first break**.

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/events` | POST | Append an event (`event_type`, `agent_id`, `payload`). F2: signed (`signature`) when the ledger holds `FIELD_LEDGER_SIGN_KEY`; with `FIELD_LEDGER_REQUIRE_SIGNING=1` and no key loaded, a start-type event is **503** (detail names the env var) and a stop-type event (`delegation.revoke`, `kill.*`, `lifecycle.decommissioned`) is 201 stamped `signing_failed: true` by the ledger — see "Per-event signatures". F2b: a body may add `caller_id`, `caller_ts`, `caller_signature` (the CALLER's Ed25519 signature); stored only after it verifies against `<caller_id>.pub.pem` in `FIELD_LEDGER_CALLER_KEYRING` — unknown caller, invalid signature, `caller_ts` outside the replay window, incomplete fields or no keyring configured ⇒ **403**, nothing written; with `FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1` a start-type body WITHOUT them is 403 (detail names the env var) and a stop-type body without them — or whose claim does not verify — is 201 with the claim dropped and `caller_unsigned: true` stamped (a stop is never refused by a caller-key fault) — see "Caller authorship" |
| `/events` | GET | Filtered read of the live segments in global order: `agent_id`, `event_type`, `since`, `until`, `limit` (the last N matches globally). `since`/`until` are inclusive ISO 8601 instants (compared as datetimes; 422 if unparseable). 503 `ledger busy` if no consistent snapshot in 5 s |
| `/verify` | GET | Walk every live segment; report the first break's GLOBAL index + reason (`segment <n>: …` on a rotated ledger, which also returns `segments`, `archived_segments`, `verified_events`, `break_segment`). A snapshot that cannot stabilise is `ok: false, reason: "ledger busy: …"` (HTTP 200) — never a tamper verdict. A record that does not parse (not JSON, or a required key missing) is a break at its GLOBAL index, `unparseable record at index <i>: …` (HTTP 200), never a 500 |
| `/export` | POST | Auditor export bundle written to `out_dir/<stamp>/` **on the ledger host** (query: `out_dir`, `since`, `until`, `agent_id`, `event_type`). Always unsigned (`signed: false`) |
| `/rotate` | POST | Close the open segment. Body `{operator, reason}` (non-blank). Signed with the Ed25519 key at `FIELD_LEDGER_ANCHOR_KEY`, read per request: unset/unreadable/unusable ⇒ 503 and nothing written. 200 returns the segment, its global range, the rotation event and the signed `anchor` (ship it off-box); 409 nothing to rotate / name taken; 503 `ledger busy` (Windows: another process holds the file); 500 corrupt |
| `/hold` | GET | `{held, hold}` — the legal hold record, if one is in place |
| `/hold` | POST | Place the legal hold. Body `{by, reason}` (non-blank, else 422). Writes `legal_hold.json`, then the `ledger.legal_hold.placed` event; 201 with the record; 409 if a hold is already in place |
| `/hold/release` | POST | Release it. Body `{by}` (non-blank). Writes the `ledger.legal_hold.released` event, then removes the marker; 409 if there is no hold |
| `/retention/apply` | POST | Archive closed segments. Body `{days, operator, archive_dir?, allow_external?}` (`days` ≥ 0; `archive_dir` default `FIELD_LEDGER_ARCHIVE_DIR`, else `FIELD_DATA_DIR/ledger-archive`, a path on the LEDGER HOST; `allow_external` must be the JSON literal `true`). 200 `{archived_segments, completed_moves, pending_moves, archive_dir, retention_event_hash}`; 423 legal hold; 422 archive dir inside the live ledger dir, outside `FIELD_DATA_DIR` without `allow_external`, on another filesystem, or a file that would be overwritten; 503 busy; 500 a segment that does not verify (not archived) |
| `/retention/check` | GET | Always 200. The estate policy `FIELD_LEDGER_RETENTION_DAYS` vs every registered agent's manifest `ledger.retention_days` (registry list, then the shared B0 resolver): `status` `ok` / `violation` / `no_estate_policy` / `unresolvable` / `unavailable`, `offending`, `unresolvable`, `agents_without_manifest`, plus `earliest_live_index`, `earliest_live_ts`, `segments`, `archived_segments`, `pending_moves`, `legal_hold`. `ok` is true only for `ok` |
| `/health` | GET | Liveness + `event_count` (GLOBAL chain length, = `/verify` length) + head hash + `earliest_live_index` / `earliest_live_ts`, from a cache (sentinel uses this). F2 adds `appendable`, `signing` (`on`/`off`/`error`), `key_fingerprint`, `seal_algorithm` (`ed25519-signed-chain` when signing is on, else `sha-256-chain`), `require_signing`, and `key_error` only when `signing` is `error` |

## CLI

```
ledger append <event_type> [--payload JSON] [--agent-id ID] [--path FILE]
                                   # signed when FIELD_LEDGER_SIGN_KEY names a usable key;
                                   # exit 2 if FIELD_LEDGER_REQUIRE_SIGNING=1 refuses it unsigned
ledger verify [--path FILE] [--genesis HASH] [--anchors FILE [--pubkey PEM]] [--event-pubkey PEM]
              [--caller-keyring DIR]
                                   # exit 1 on first break (or, with --event-pubkey, the first
                                   # invalid per-event signature, naming its index; with
                                   # --caller-keyring, the first unknown caller or invalid
                                   # caller signature, naming its index), 4 if busy
ledger anchor --anchors FILE [--key PEM] [--path FILE]
ledger export [--out-dir DIR] [--path FILE] [--since ISO] [--until ISO]
              [--agent-id ID] [--event-type TYPE] [--sign-key PEM]
ledger verify-export BUNDLE_DIR [--pubkey PEM]   # exit 1 on failure, naming the first failing index when it has one
ledger rotate --operator NAME --reason TEXT [--anchors FILE]
              [--offline [--path FILE] [--key PEM]]
ledger hold place --by NAME --reason TEXT [--offline [--path FILE]]
ledger hold release --by NAME [--offline [--path FILE]]
                                   # exit 2 blank name / already held / no hold; 4 busy
ledger retention apply --days N --operator NAME [--archive-dir DIR] [--allow-external]
                       [--offline [--path FILE]]
                                   # exit 0 done (also when nothing was due); 1 a segment does
                                   # not verify; 2 refused; 4 legal hold or busy
ledger retention check [--offline [--path FILE]]   # prints the JSON; exit 0 ok, 3 otherwise
ledger witness run --estate NAME --fly-url https://ORIGIN [--every SECONDS] [--once]
                                   # X4: long-running (first tick at start); --once: exit 0 iff
                                   # direction 1 appended, else 1; 2 usage
ledger verify-witness --estate NAME (--events-url URL [--secret-file F] | --events-file F)
                      [--path FILE] [--pubkey PEM]
                                   # exit 0 only if every anchor holds and >= 1 with length >= 1
                                   # held; 1 otherwise; 2 usage / source unreadable; 4 busy
ledger serve [--host H] [--port 8002]
```

`ledger verify --path X` picks its mode from X: the open segment of a rotated
ledger (`<stem>.segments.journal` beside it) ⇒ every live segment, plus a line
`(<k> segments, <a> archived; <m> events hash-verified)`; a live closed segment
`<stem>-<n><suffix>` named in that journal ⇒ that segment alone against its
journal entry (`OK — segment <n> of <logical> intact over <K> events (global
<a>..<b>)`; `--anchors` refused) — also a segment journaled as archived but
not yet moved (a pending move: its bytes must match the sha-256 journaled at
archival) and a pending rotation's renamed file, each with a note line; an ARCHIVED segment (its
`<file>.segment.json` sidecar beside it) ⇒ that file from its sidecar, same OK
line, plus the signed rotation anchor when `--pubkey` is given (`--anchors`
refused); `--genesis HASH` ⇒ X alone, starting from that `prev_hash`; anything
else ⇒ a single file from the genesis hash, exactly as before rotation existed. It never writes (a crashed rotation is finished by
the service or the next write, not by a verify).

`ledger rotate` goes through the running service when `FIELD_LEDGER_URL` is set
(the service's key, lock and caches stay authoritative); without it, it refuses
unless `--offline` (files directly, key from `--key` or
`FIELD_LEDGER_ANCHOR_KEY`). Exit 0 rotated; 1 corrupt; 2 refused / no usable
key / usage; 4 busy. `--anchors FILE` appends the signed rotation anchor.
`ledger hold` and `ledger retention` delegate the same way (`--path` only with
`--offline`). On Fly the service cannot be stopped: use the served routes.

## Per-event signatures (v1.2 F2)

Every event the ledger process writes — appends, hold and retention events,
the rotation event — carries a `signature` when the process holds a key.

**Env vars** (read ONCE at store/app start; the CLI reads the same two, so an
offline `ledger append --path` on the box signs like the service):

| Var | Meaning |
|---|---|
| `FIELD_LEDGER_SIGN_KEY` | PEM path of the Ed25519 private key (the format `field_core.signing.generate_keypair` writes; the estates generate it with `tools/volume_admin.py … keys generate ledger-sign`). Unset/blank ⇒ `signing: off`, events unsigned, exactly today's lines. A path that is missing, unreadable or not an Ed25519 private key is **never a process exit**: the service starts, `/health` says `signing: error` with a one-line `key_error` (the failure class and the env var name, never key material), and behaviour follows the next var. It is a SEPARATE key from `FIELD_LEDGER_ANCHOR_KEY` (rotation anchors, archived-segment sidecars, witness anchors), which is never used for events |
| `FIELD_LEDGER_REQUIRE_SIGNING` | `1` (default `0`): with no key loaded (`off` or `error`) the ledger is not `appendable`: every START-type append is refused **503** naming the env var, nothing written — the `conformance.allow` a sentinel in enforce mode needs included, which is why it then BLOCKs `L.unreachable`. STOP-type events are the exception: exactly `delegation.revoke`, every `kill.*` and `lifecycle.decommissioned` (`sealed_ledger.store.is_stop_type`, one function) are accepted unsigned with `signing_failed: true` stamped by the ledger (the caller sends nothing new), because refusing them would keep an agent alive or a token valid. Rotation, hold placement and retention apply are refused the same way before anything is written or moved. With `0` and no key, every append is unsigned with NO `signing_failed` key (today's behaviour); with `0` and a key in `error`, appends are unsigned and `/health` shows the error — the A7 soak check (`signing: on`, `appendable: true`) catches a key that never loaded |

**What is signed.** Hash first, sign second: `signature` is base64 of the raw
64-byte Ed25519 signature over the canonical record (sorted keys, compact
UTF-8 JSON) INCLUDING `hash` and EXCLUDING `signature`
(`field_core.ledger.event_signing_bytes`; `sign_event` / `verify_event_signature`
in `field_core.signing`). `compute_event_hash` pops `signature` exactly as it
pops `hash`, so every pre-F2 hash is unchanged and every tamper test keeps its
meaning. `signing_failed` is INSIDE the hash (stamped before sealing):
stripping it from a line is a chain break, not a downgrade. Both fields are
`None` by default and OMITTED from the JSON line when `None`, so an unsigned
append's line is byte-identical to a pre-F2 line and images already deployed
(`extra="forbid"`) keep parsing unsigned records; the first SIGNED event is
what makes a pre-F2 image unable to read the file (the reversibility table).

**`/health`** gains `appendable` (false exactly when `FIELD_LEDGER_REQUIRE_SIGNING=1`
and no key is loaded), `signing` (`on` | `off` | `error`), `key_fingerprint`
(sha-256 over the raw 32-byte public key — the same value `keys-admin` and
`field_core.signing.key_fingerprint` print, `None` unless `on`), `seal_algorithm`
(`ed25519-signed-chain` when `on`, else `sha-256-chain`; both are field-core
`SEAL_ALGORITHMS`), `require_signing`, and `key_error` ONLY when `signing` is
`error`. Every pre-F2 field stays.

**Verifying.** `ledger verify --event-pubkey <pem>` takes the SIGN public key
(`ledger-sign.pub.pem`); `--pubkey` stays the ANCHOR key — the plan's
"`verify --pubkey` (existing flag)" wording cannot hold because REVISION 2.1
made the two keys separate, so a second flag was added. After the chain walk
(and before `--anchors`), every event that carries `signature` must verify;
the first that does not is `SIGNATURE INVALID — index <i>: …`, exit 1.
Unsigned events are reported, never failed (pre-F2 history and stop-type
events are legal unsigned), in exactly one line:
`signed <n> unsigned <m> first_unsigned_index <i|none> first_signing_failed_index <i|none> first_unsigned_after_signed <i|none>`
(global indices; on `--genesis` the indices are local to the file). Every
mode of `verify` checks signatures (whole ledger, a live closed segment, an
archived segment from its sidecar, `--genesis`). Served `GET /verify` is
unchanged (chain only). `ledger verify-export` on a C1 bundle carrying signed
events passes: events are exported verbatim, signature included, and the
bundle's hash recompute ignores it.

**What a signature proves, and what it does not.** A valid signature proves
that *the ledger process holding the key wrote this record* — not who asked
it to (the appending caller is still any holder of the perimeter secret;
caller authorship is the caller's OWN signature — "Caller authorship (v1.2
F2b, GB10)" below, Enforced on the GB10 once its keyring is armed, Declared
on Fly). The key is on the box
(`/data/keys/ledger-sign.pem`, read-only into the ledger only on the GB10),
so this is tamper-evidence against actors WITHOUT box access only: an
attacker who edits a signed event and re-links every later hash passes plain
`verify` and is caught at that index by `--event-pubkey`; one who also drops
that event's `signature` is still caught at the NEXT signed event (its
`prev_hash` is under its signature) — only the TAIL can be replaced
unsigned, and that shows up as `first_unsigned_after_signed` and a changed
unsigned count, which is why the A7/A9 checks compare the unsigned count with
the pre-F2 count. Someone holding the key, or root on the box, can re-sign
anything.

**Fault path (A9) is CI-proven, not live.** `integration/demo/fixtures/upgrade-smoke/signing_fault.py`
runs in `compose-upgrade-smoke` against a ledger recreated with an unreadable
key and `REQUIRE_SIGNING=1`: `/health` `appendable: false`, `/sentinel/check`
⇒ BLOCK `L.unreachable`, `registry.updated` ⇒ 503, `kill.agent` ⇒ 201
`signing_failed: true`. On a live estate that state would BLOCK every agent.

## Caller authorship (v1.2 F2b, GB10)

F2's `signature` proves the LEDGER wrote a record. F2b adds the CALLER's
signature: each appending service holds its own Ed25519 key, mounted only
into it, and signs what it asks the ledger to append; the ledger verifies
the claim against that service's recorded public key before writing, and
stores the claim in the event, inside the hash and under its own signature.

**What a caller signature proves, and what it does not.** A stored
`caller_signature` proves that *the service holding that key asked for this
append* — with exactly this `event_type`, `agent_id`, `payload` and at
`caller_ts` — not that the append was justified (a compromised or
misconfigured sentinel signs its own mistakes), and not who is behind the
service. The private keys are on the box (bind-mounted read-only, one per
container, outside every volume and backup), so this is evidence against
actors WITHOUT box access: root on the GB10 holds every key. Unsigned events
are legal (pre-F2b history, the ledger's own events, stop-type events under
the require switch), so `verify --caller-keyring` REPORTS them and never
fails them; what it fails is a claim that does not verify.

**Caller side** (`field_core.clients.LedgerClient.append`; the witness's own
client does the same). When BOTH `FIELD_LEDGER_CALLER_ID` and
`FIELD_LEDGER_CALLER_KEY` (a PEM path, Ed25519 private, the
`generate_keypair` format) are set and the key loads, the `POST /events`
body gains `caller_id`, `caller_ts` (ISO 8601 UTC, now) and
`caller_signature` = base64 of the raw Ed25519 signature over the canonical
bytes (sorted keys, compact UTF-8 JSON; `field_core.signing.caller_signing_bytes`)
of exactly `{event_type, agent_id, payload, caller_id, caller_ts}`. Both
unset ⇒ the body is exactly the pre-F2b body. Set but unloadable (missing,
unreadable, not an Ed25519 private key, or only one of the two set) ⇒ the
service appends UNSIGNED and logs one warning per process — never an
exception, because a caller must still be able to revoke and kill; the
ledger's require switch is the enforcement point. The key is loaded once per
client, never per append. `caller_id` is the sentinel's, gateway's and
crosswalk's self-agent id (`conformance-sentinel`, `force-gateway`,
`compliance-crosswalk`); every other service uses its compose service name
(`registry`, `delegation`, `killswitch`, `governor`, `replay`, `fedbroker`,
`console`, `lifecycle`, `attest`, `witness`). A caller id must match
`^[a-z0-9][a-z0-9-]{0,62}$` (the `keys-admin` name rule): it names a keyring
FILE and never reaches outside the keyring directory.

**Ledger side.** Env vars, read ONCE at store/app start:

| Var | Meaning |
|---|---|
| `FIELD_LEDGER_CALLER_KEYRING` | Directory of `<caller_id>.pub.pem` files (GB10: `/data/keys/callers` on the existing read-only `field-keys` volume; written only by `keys-admin import-public`). Set ⇒ `/health` `caller_keyring: on` and `caller_keys: <count>`. The files are read on lookup (mtime/size cache), so a key imported after the ledger started needs no restart, and a rotated caller key is followed. Unset/blank ⇒ `off`: a body carrying caller fields is **403** `caller keyring not configured` — an unverifiable claim is never silently accepted; a body without them is what it always was. A path that does not exist is `on` with `caller_keys: 0` (every caller unknown), never a process exit |
| `FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE` | `1` (default `0`): a START-type append with no caller fields is refused **403** naming the env var, nothing written. STOP-type events (F2's `is_stop_type`: exactly `delegation.revoke`, every `kill.*`, `lifecycle.decommissioned`) are accepted and stamped `caller_unsigned: true` by the ledger (inside the hash; omitted otherwise), because refusing them would keep an agent alive. A stop-type body that PRESENTS a claim which does not verify (unknown caller, invalid signature, stale `caller_ts`, incomplete fields, no keyring) lands the same way — 201, the bad claim DROPPED (never stored) and `caller_unsigned: true` stamped, the refusal reason in the ledger's log — because a stop must never be refused by a caller-key fault (F2's principle), and a perimeter-secret holder can already append that stop-type event with no claim at all, so accepting a bad claim as unsigned is no worse. With the switch OFF (the default) a bad claim on ANY type is **403**: an unverifiable claim is never stored, and the operator has not asked for fail-safe stops. The ledger's own events — the offline `ledger append`, hold placement and release, rotation, retention apply — are not served appends and are never subject to it (they carry the ledger's own F2 `signature`) |

A served append with caller fields is refused **403** (nothing written, not
even the lock file) when: any of the three is missing or blank (`incomplete
caller fields`); no keyring is configured; `caller_id` fails the name rule or
has no `<caller_id>.pub.pem` (or the file is not an Ed25519 PUBLIC key) —
`unknown caller`; `caller_ts` is not an ISO 8601 instant, is older than
**300 s** or more than **60 s** in the future (the replay window; naive
instants are UTC) — `refused: caller_ts …`; or the signature does not verify
over `event_type`, `agent_id`, `payload`, `caller_id`, `caller_ts` — `invalid
caller signature`. (The one exception: under
`FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1` a STOP-type append with any of
those faults lands with the claim dropped and `caller_unsigned: true`
instead — the table above.) Otherwise the event stores `caller_id`, `caller_ts`,
`caller_signature` as top-level fields; all three (and `caller_unsigned`) are
OMITTED when absent, so an unsigned append's line is still byte-identical to
a pre-F2 line and images already deployed keep parsing it. Hash first,
ledger-sign second: the caller fields are inside `hash`, so F2's `signature`
covers them — an attacker who edits `caller_id` and re-links is caught by
`--event-pubkey` as well as by `--caller-keyring`. A ledger WITHOUT F2b
ignores the three body fields (the request model never forbade extras): a
rolled-back ledger image silently drops the claim, which the A7b live check
(below) would show as a `conformance.allow` with no `caller_id`.

**`/health`** gains `caller_keyring` (`on` | `off`), `caller_keys` (the
`*.pub.pem` count, 0 when off or unreadable) and `require_caller_signature`.
Every F2 and pre-F2 field stays.

**Verifying.** `ledger verify --caller-keyring <dir>` (in the ledger container:
`/data/keys/callers`): after the chain walk (and after `--event-pubkey`, before
`--anchors`), every event carrying `caller_signature` must name a caller with
a usable key in the directory and verify under it; the first that does not is
`CALLER UNKNOWN — index <i>: …` or `CALLER SIGNATURE INVALID — index <i>: …`,
exit 1. Then exactly one line:
`caller_signed <n> caller_unsigned <m> per_caller {id: n, ...} first_caller_unsigned_after_signed <i|none>`
(`caller_unsigned` = events with no caller signature, the stamped stop-type
events included; global indices, local on `--genesis`). Every mode of
`verify` checks it (whole ledger, a live closed segment, an archived segment
from its sidecar, `--genesis`). The replay window is not re-checked at
verify time (`caller_ts` was checked at append time and is history now).
Served `GET /verify` is unchanged (chain only). Export bundles carry the
caller fields verbatim and `verify-export` passes.

**Keyring writer.** `tools/volume_admin.py keys import-public --dir /keys/callers <caller_id>`
(the `keys-admin` one-shot on the GB10, `-T` with the PEM on stdin) reads ONE
public PEM, refuses anything that is not an Ed25519 PUBLIC key (a private key
piped by mistake: exit 2, never echoed), writes `<caller_id>.pub.pem` (0644,
re-encoded from the parsed key, never overwriting) and prints the
fingerprint. Each service's PRIVATE key is generated on the host with `keys
generate` into a per-service directory and bind-mounted read-only into that
service alone (`/run/caller-key/<id>.pem`); it is on no volume and in no backup.

**Arming order (GB10, runbook §4 "A7b").** Keyring and per-service keys
FIRST — `FIELD_LEDGER_CALLER_KEYRING=/data/keys/callers`, the callers'
`FIELD_LEDGER_CALLER_ID` / `FIELD_LEDGER_CALLER_KEY`, each service recreated
— with `FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=0`: every append is already
signed and verified, and a service whose key did not load still appends
(unsigned, one warning). Live check: one canary `/check` ⇒ the new
`conformance.allow` carries `caller_id: conformance-sentinel`, and `ledger
verify --caller-keyring /data/keys/callers` exits 0 with `per_caller`
including it. REQUIRE LAST, after a soak in which the unsigned count stops
growing: from then on a service with an unloadable key has its start-type
appends refused (the sentinel's `conformance.allow` included — it then
BLOCKs `L.unreachable`, as under A9). Disarm: remove the REQUIRE line and
recreate the ledger; the stored claims stay. To switch caller signing OFF
entirely the order reverses: remove the callers' two env lines and recreate
the CALLERS first, and only then remove `FIELD_LEDGER_CALLER_KEYRING` and
recreate the ledger — a ledger with no keyring refuses every body that still
carries caller fields (403), so a keyring removed while the services still
sign stops every one of them appending.

**On-box limit, and Fly.** Every caller key and the keyring live on one host:
root on the GB10 can read any service's key and sign as it, so caller
authorship is evidence against actors without box access, including a
perimeter-secret holder who is not a platform service. Fly keeps the (b) row:
a single container in which every process can read every key, so a per-service
key proves nothing there — not deployed, `caller_keyring: off`, appends unsigned.

## Retention (C2): rotation, archival, legal hold, retention check

**Retention is ESTATE-level.** One shared chain per estate, so there is no
per-agent deletion and no per-agent retention. `FIELD_LEDGER_RETENTION_DAYS`
(compose/Fly `2555`) is the estate policy; each manifest's
`ledger.retention_days` is a FLOOR the estate must meet, not a per-agent purge.
Nothing in the platform deletes ledger data: rotation closes the open segment,
retention apply moves closed segments to an archive directory, and what
happens to that directory afterwards is the operator's.

Rotation closes the open segment; the chain continues unbroken:

| File (beside the path given, e.g. `ledger/events.jsonl`) | What |
|---|---|
| `events.jsonl` | ALWAYS the open segment. A ledger that never rotated is exactly the old single file |
| `events-<n>.jsonl` | closed segment n (the old open file, renamed). Its successor's first line is a `ledger.segment.rotated` event carrying `operator`, `reason`, the closed range and head, and a signed anchor `{anchored_at, chain_length, head_hash, segment}`; its `prev_hash` is the closed head |
| `events.segments.journal` | append-only JSONL: `rotate-intent` (fsynced before any rename), `rotate-commit` / `rotate-abort`, and `archive` (reserved for retention apply). Its absence is what makes a ledger single-file. Closed segments are found only through it |
| `.events.jsonl.lock` | 0-byte cross-process writer lock, created by the first write |
| `.events.jsonl.rotating` | transient: the new open segment, written and fsynced before the rename |
| `legal_hold.json` | the legal hold `{placed_at, placed_by, reason}`; its EXISTENCE is the hold |
| `<archive dir>/events-<n>.jsonl` | an archived closed segment (the same file, renamed — never copied) |
| `<archive dir>/events-<n>.jsonl.segment.json` | its sidecar: `n`, `file`, `start_index`, `end_index`, `genesis_prev_hash`, `head_hash`, the signed rotation `anchor`, `closed_at`, `closing_rotation_event_hash`, `sha256` of the file, `archived_by` |

Global indices never renumber. Step order: intent → new segment tmp → rename the
open file to `events-<n>.jsonl` → rename the tmp into place → commit. A process
killed at any step leaves the full chain readable, and the next write (or the
service at startup, only if a rotation is pending) finishes or undoes it.
Readers take no lock: each read is a snapshot validated against the journal
bytes and the existence of the two paths a rotation changes; on Windows every
read opens files with FILE_SHARE_DELETE so it never blocks the rename.

**Retention apply** (`ledger retention apply --days N`, `POST /retention/apply`)
archives closed segments whose `closed_at` is more than N days old, oldest
first, never the open segment; the first segment that is too young stops the
run, so archived segments are always a prefix. The archive directory must be
under `FIELD_DATA_DIR` (else `--allow-external`), must not be the live ledger
directory or inside it, and must be on the same filesystem (archival renames;
it never copies). Per segment: verify it against the journal entry AND the
hash-chained rotation event that opens its successor → write the sidecar →
journal `archive` op under both writer locks (from here readers skip the file)
→ `os.rename` outside the locks, never overwriting. A file another process
holds open (Windows) is left as a pending move that the next apply completes.
One `ledger.retention.applied` event per run that archived or completed
anything (its `archive_evidence` names, with their sha-256, the segments
that run archived plus every archived segment an earlier live event already
named); a run with nothing to do writes nothing. After archival `verify` is
still ok with the global length (`archived_segments` counted), `/events`
returns live events only, and `/health` `earliest_live_index` /
`earliest_live_ts` move.

**Legal hold** (`ledger hold place --by NAME --reason TEXT`, `ledger hold
release --by NAME`): while `legal_hold.json` exists, retention apply refuses
(exit 4 / HTTP 423), and the hold is checked again under the writer lock
before each journal commit. Place writes the file first and the event second;
release writes the event first and removes the file second — a crash in
between always leaves the hold in force.

**Retention check** (`ledger retention check`, `GET /retention/check`) lists
every registered agent (from inside the ledger container:
`FIELD_REGISTRY_URL`, `FIELD_MANIFEST_DIR`), resolves its `manifest_ref` with the
shared B0 resolver and compares `ledger.retention_days` with the estate policy.
Agents with NO `manifest_ref` are skipped and counted; a SET ref that does not
resolve is `unresolvable`; no policy is `no_estate_policy`; a registry the
ledger cannot read is `unavailable`. Any of those, or an offending manifest,
is not ok (exit 3). It reports; it never archives or refuses anything.

What each piece proves: archived segments are verified by journal link only —
the journal is not tamper-evident; the signed rotation anchor (shipped
off-box) pins each closed head; the hold marker is only as strong as file
access; the rotation key is on the box, so all of it is tamper-evidence only
against actors without box access. A journal `archive` record is not taken
on its word, and every archived segment needs its own evidence: live
`verify` reads an "archived" file that is still in the ledger directory;
otherwise a hash-chained `ledger.retention.applied` event in the live chain
must name that segment with the sha-256 the record journals; otherwise its
archive copy must be present and verify. Retention apply refuses to run on a
ledger whose live verify breaks, so it never archives past such a record.
What that does NOT stop: someone who can append to the journal AND append a
correctly linked `ledger.retention.applied` event naming the segment and
that digest (any API client can post that event type) can drop the oldest
live segment from plain `verify` — the same class as re-linking the tail;
anchors over that range still fail. An appended `archive` record over
segment bytes that are still intact verifies, and those events leave
`/events`.

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

## Cross-estate witnessing (X4)

`ledger witness run` is the GB10 compose service `witness`
(`integration/demo/docker-compose.gb10.yml`, arming step A5), behind the
compose profile `witness`: no plain `up` starts it until A5 puts
`COMPOSE_PROFILES=witness` and `FIELD_WITNESS_EVERY` in the GB10 `.env`. Each tick —
the first at start, then every `--every` seconds (`FIELD_WITNESS_EVERY`,
3600) — it loads the anchor key (`FIELD_LEDGER_ANCHOR_KEY`, the on-box key,
mounted read-only into the witness) and then:

- **Direction 1 (live, no cross-estate secret).** `GET <fly-url>/ledger/health`
  (Fly's open route; https only, certificate verified, 10 s timeout, redirects
  never followed), then ONE `anchor.remote` appended to the LOCAL ledger through
  `FIELD_LEDGER_URL` with the local perimeter header. Payload `{estate: "fly",
  length: <Fly event_count = its global length>, head_hash, observed_at (UTC),
  observer: {role: "witness", host: <container hostname>, started_at: <process
  start UTC>}, key_fingerprint, signature}`; `signature` is Ed25519 over the
  canonical JSON (sorted keys, compact) of every other payload field, signed in
  the witness process. No served route signs anything.
- **Direction 2 (NOT live until D5).** Only when `FIELD_WITNESS_FLY_SECRET_FILE`
  names a readable, non-empty file: the local head, as `anchor.remote{estate:
  <--estate>}` signed the same way, is POSTed to `<fly-url>/ledger/events`
  with that file's secret as `x-field-auth`. Unset ⇒ every tick logs
  `direction 2 not live (D5)`.

A failed Fly read, a non-200, a redirect or an answer that is not a head
appends nothing and logs one line; an unusable key appends nothing, contacts
nothing and the loop keeps running. Secrets are redacted from every log line; a
refusal body is redacted in full BEFORE it is cut to 200 characters, so a secret
straddling the cut leaves no prefix behind.

`ledger verify-witness --estate NAME` loads every `anchor.remote` whose
`payload.estate == NAME` from its source (a ledger's `/events` route, which
serves only that ledger's LIVE segments, or a copied JSON array / JSONL file; a
repeated JSON key anywhere refuses the source; a redirect is never followed, so
`--secret-file`'s header never reaches another host), verifies
the LOCAL chain (`--path`), then checks each anchor against the length that verification covered: the hash at global index
`length - 1` must equal `head_hash`; a length beyond the local chain is
`witnessed a future head`; an index in an archived segment is an explicit
failure naming the segment; with `--pubkey` the signature must verify and
`key_fingerprint` must be that key's. One line per anchor, then a summary; zero
anchors is `nothing witnessed`, exit 1, and so is a set whose only holding
anchors have length 0 (the genesis head holds against ANY chain, so it witnesses
nothing). On Fly: `--events-file` (the GB10's
`anchor.remote` events copied out) `--pubkey` (the GB10 anchor public key). On
the GB10, direction 2 would be checked with `--events-url` to Fly and the Fly
secret — not live until D5. Procedure: `docs/runbooks/v1.2-deploy-rollback.md`, "X4 witness (A5)".

The lifecycle sweep reports a `witness` finding (exit 3, `/findings`) where
`FIELD_WITNESS_EVERY` is set: see `services/lifecycle-manager/README.md`.

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Every event is hash-linked to its predecessor | **Enforced in code** | `store.append` seals under an in-process lock and a cross-process lock file; genesis links to 64 zeros; the first event of every segment after a rotation links to the closed head |
| A naive on-disk mutation or deletion of a mid-chain record is detectable | **Enforced in code** | `verify` recomputes every hash + link in every LIVE segment; adversarial tests mutate and delete mid-chain records on disk and prove detection. On a rotated ledger the break names the segment and the GLOBAL index (`tests/test_ledger_rotation.py::test_tamper_inside_live_closed_segment_names_segment_and_global_index` at global 2 / 6 / 10, `test_genesis_link_edit_breaks_at_its_first_index`). A closed segment rewritten inside itself (same count, links intact, only its head moved) breaks at its last index against the journal's `head_hash`, in the store walk and in `ledger verify --path <closed file>` (`tests/test_ledger_c2_hardening.py::test_a_closed_segment_rewritten_inside_itself_breaks_at_its_head`). A segment journaled as archived whose file is still in the ledger directory is read like a live one — chain, count, head against the journal's `head_hash`, bytes against the sha-256 journaled at archival (`test_forged_archive_ops_cannot_hide_segments_still_in_the_ledger_directory`, `test_an_archived_file_still_in_the_ledger_dir_rewritten_inside_itself_breaks_at_its_head`, `test_cli_verify_of_a_pending_move_checks_its_journal_entry_and_digest`). A record that does not parse is a break at its global index, single-file or segmented, on a store opened before or after the edit (`test_an_unparseable_record_is_a_break_on_verify_never_a_500`; an earlier real break keeps its own index: `test_an_earlier_real_break_keeps_its_index_before_an_unparseable_record`) — but a store cannot be OPENED on an open segment holding such a line (see LIMITS). NOT covered here: deleting the tail, or mutating a record and re-hashing and re-linking every record after it, passes plain `verify` — only the anchor row below catches those. A segment moved to an archive is read by live `verify` only when no `ledger.retention.applied` event names it with its sha-256 (then its archive copy must verify, see the journal row); otherwise its head is pinned only by the next rotation event, and an archived record is checked by `ledger verify --path <archived file>` from its sidecar (the sidecar row below) |
| Appends are durable when acknowledged | **Enforced in code** | flush + fsync before returning |
| Auditor export is re-verifiable offline (hashes + spine); Ed25519-signed only via `ledger export --sign-key` — the served `/export` is unsigned (`signed: false`) | **Enforced in code** | `verify-export` recomputes every exported hash against the spine, walks the spine to `head_hash`, recomputes counts, checks the signature. `tests/test_export_bundle.py`: one edited event ⇒ exit 1 naming its index; a deleted line fails; a filtered (agent_id) export of an interleaved two-agent chain verifies via the spine and prints "spine unverified" when unsigned; `summary.json` tampered on a signed bundle fails; wrong key fails; unsigned + `--pubkey` fails; the served route writes `signed: false` |
| A bundle that records no filter exports every index `0..head_index` (deleting an event fails when the indices and counts are re-edited but `head_index`/`head_hash` are not), and no bundle file or event line may repeat a key | **Enforced in code** | The recorded filters and the head of an UNSIGNED bundle can themselves be edited: a deletion that also rewrites `head_index`/`head_hash` verifies, so an auditor relying on completeness must see `filters: none` in the output AND a printed `head_hash` equal to a pinned/anchored head (or a valid signature under `--pubkey`). `summary.json` accepts unknown keys, so an extra, differently-named key is not refused. `tests/test_export_bundle.py`: middle, tail, head deletion and an emptied bundle each fail with `summary.json`/`chain_proof.json` re-edited (`test_deleting_a_middle_event_from_an_unfiltered_bundle_fails_even_with_summary_reedited`, `test_dropping_the_tail_…`, `test_dropping_the_first_events_…`, `test_emptying_an_unfiltered_bundle_fails`); a non-genesis start at index 0 fails; duplicate-key decoys in an event line (signed, genuine key) and in each JSON file fail; genuine U+2028/U+2029/NEL payloads verify. On a rotated ledger indices are global and the rule is every LIVE index `earliest..head_index` (`test_export_of_a_rotated_ledger_uses_global_indices`, `test_export_after_archival_starts_at_the_earliest_live_index`). The archived prefix is read from the bundle's own verification dict, so an editor of an UNSIGNED bundle can drop whole leading segments that end at a rotation boundary and claim them archived: it verifies, and `verify-export` PRINTS `indices 0..E-1 are archived`; a signature under `--pubkey` catches it (`test_unsigned_bundle_can_claim_an_archived_prefix_but_not_under_signature`). A claimed prefix must still be consistent: no exported index below it (`tests/test_ledger_c2_hardening.py::test_a_bundle_exporting_an_index_below_its_claimed_archived_prefix_fails`), and its first live event must be a rotation event closing it whose recorded head is the hash it links to (`test_a_claimed_archived_prefix_must_end_at_a_rotation_event_that_links_to_its_head`) |
| `verify-export` never presents an unsigned bundle as proof of what the ledger holds | **Enforced in code** | unsigned (or no `--pubkey`) prints "spine unverified"; unsigned + `--pubkey` exits 1; `test_unsigned_filtered_bundle_cannot_detect_a_relinked_forgery` pins the limit: an unsigned bundle is internal consistency only, and independent proof = `head_hash` compared with an off-box anchor (covering the exported events only for a contiguous bundle); a `--until` window that ends before head is reported `filtered:`, never `contiguous:` (`test_a_windowed_export_that_ends_before_head_is_not_contiguous`) |
| A filtered export is complete (every matching event included) | **Declared only** | the spine carries only hashes for events it does not export, so a verifier cannot re-run the filter |
| Time windows are exact (ISO 8601 instants, both bounds inclusive) | **Enforced in code** | `datetime.fromisoformat`, naive ⇒ UTC (`sealed_ledger/filters.py`); `tests/test_time_filters.py`: `Z` vs `+00:00`, mixed offsets, exact-bound inclusivity, garbage ⇒ 422 |
| Nobody can rewrite history *undetectably* | **Declared only** | plain `verify` is blind to a self-consistent full rewrite (`test_adversarial_full_history_rewrite_beats_verify_but_not_anchors` asserts it passes); detection needs the anchor row below with the anchor file held off-box, which is deployment responsibility |
| Full-history rewrites are detectable against anchors | **Enforced in code** | `ledger anchor` pins (length, head hash); `verify --anchors` demands the chain still contain them — adversarial test proves a self-consistent forgery passes plain verify but fails the anchor check. Signed anchors (Ed25519) make the anchor file itself tamper-evident |
| A rotated ledger is still one chain: global indices never renumber, `/verify` length and `/health` `event_count` are the global length, `/events` spans live segments | **Enforced in code** | `tests/test_ledger_rotation.py::test_rotate_twice_verify_ok_across_three_segments` (11 events over 3 segments, line k of each file = global start + k), `test_store_opened_as_e_jsonl_rotates`, `test_events_agent_id_spans_segments` |
| Editing or deleting the segments journal is detected, not trusted | **Enforced in code** — NARROWED (see the last sentence) | every journal field of a closed segment must equal the hash-chained rotation event that opens the next live segment, each field edited alone (`tests/test_ledger_c2_hardening.py::test_an_edit_of_each_journal_field_of_an_archived_segment_is_detected` for `start_index`, `end_index`, `genesis_prev_hash`, `file`, `anchor`, `head_hash`; `test_a_renamed_live_closed_segment_with_its_journal_file_edited_is_detected`; `test_a_segment_boundary_at_an_event_that_is_not_its_rotation_event_is_detected`); every record must carry the fields and JSON types its op needs, follow the state machine and start each segment from the previous head, else it is an invalid line (`test_a_journal_record_missing_a_field_is_a_break_never_a_crash`, `test_each_journal_state_machine_rule_is_a_break`, `test_a_journal_intent_that_does_not_start_from_the_previous_head_is_invalid`); an invalid line is a break reported AFTER the walk — an earlier real break keeps its own index (`test_a_bad_journal_line_does_not_hide_an_earlier_break`) — and every write is refused (HTTP 500); an `archive` record is not trusted on its own, and EVERY archived entry needs its own evidence — none is excused because a later one is evidenced: an "archived" file still in the ledger directory is verified (chain, count, head, sha-256); otherwise a hash-chained `ledger.retention.applied` event in the live chain must name that segment number WITH the sha-256 the entry journals (payload `archive_evidence`; the digest-less `archived_segments` list is not evidence); otherwise its archive copy at `archived_to` must be present and verify. Retention apply's event names the segments that run committed plus every entry an earlier LIVE event already named (so evidence survives the archival of the segment holding an older event); an entry evidenced only by its bytes — a killed run's, or a forged line over intact bytes — is never promoted into an event. So appended forged `archive` lines over a deleted or edited segment are a break however many are appended, and retention apply refuses to archive past them (`test_forged_archive_op_over_a_deleted_segment_is_a_break_and_apply_will_not_launder_it`, `test_every_archived_entry_needs_its_own_evidence_two_forged_lines` — one line over a deleted `events-1.jsonl`, one carrying the real sha-256 of an intact `events-2.jsonl` left in place or moved to its `archived_to`, with and without a digest-less event — `test_bytes_only_evidence_is_never_promoted_by_a_later_apply`, `test_retention_events_carry_every_evidenced_archive_forward`, `test_forged_archive_ops_cannot_hide_segments_still_in_the_ledger_directory`, `test_an_archival_whose_event_never_landed_is_verified_from_its_archive_copy`). Also `test_journal_edit_of_archived_head_breaks_live_verify_at_next_segment_first_index`, `test_deleting_journal_is_loud` (`link break at index 0`), `test_invalid_complete_journal_line_is_a_break_and_refuses_writes`. The journal itself is not signed: for the NEWEST closed segment the pin is the open segment's first event, and an archived segment's range is pinned only while its successor is live. NOT detected: (a) appending an `archive` line to the journal AND appending a correctly linked `ledger.retention.applied` event whose `archive_evidence` names that segment with the sha-256 the line journals (any API client can post that type) drops a deleted oldest live segment from plain `verify` — the re-link class of the mid-chain row; an anchor over that range still fails (pinned by `test_forged_archive_op_plus_a_forged_retention_event_is_the_documented_limit`, which also shows an event naming another digest is not evidence); (b) an appended `archive` line whose segment bytes are intact — left in the ledger directory, or copied to the `archived_to` it names — verifies (the bytes are its evidence), so that segment's events leave `/events` and `/export` while its file still holds them (`test_bytes_only_evidence_is_never_promoted_by_a_later_apply` pins that it verifies until the file is deleted) |
| Rotation is never unsigned; a missing or bad anchor key is a 503, never a process exit | **Enforced in code** | `FIELD_LEDGER_ANCHOR_KEY` is read and checked (PEM, Ed25519) per request. `test_rotate_without_key_503` (unset, missing file, directory, garbage, EC key: 503, directory unchanged, the app keeps serving and still builds); `tests/test_ledger_c2_hardening.py::test_rotate_with_a_key_of_an_unknown_algorithm_is_503` (a PKCS#8 key whose algorithm OID cryptography does not know: `UnsupportedAlgorithm` is 503, not 500); `test_ledger_latency_100k.py::test_served_latency_100k_under_verify_readers_and_rotation` (real `ledger serve` process: unreadable key ⇒ 503, process alive, key written ⇒ rotation 200; runs with `FIELD_SLOW_TESTS=1`) |
| A process killed at any step of a rotation never leaves a silent new genesis or a silently shortened chain | **Enforced in code** (process kills) | `tests/test_ledger_crash_points.py`: killed at each of 9 named steps, first and second rotation (18 cases) ⇒ a fresh read is the full chain and changes no file, and a restart rolls the rotation back or forward with the first hash unchanged; a syscall-level sweep kills before every mutating call of append/append/rotate/append/append/rotate/append (37 crash points on Windows) ⇒ every read full, every restart recovered; with `FIELD_SLOW_TESTS=1` every restart that does recovery work is itself killed at each call (294 double-crash runs on Windows, every read the full chain — asserted `== "full"` since the C2 review — and all recovered). Power loss is NOT tested, and Windows cannot fsync a directory |
| No reader in this code sees an empty or short chain that verifies ok while the ledger rotates | **Enforced in code** | `tests/test_ledger_readers.py`: a writer thread parked before each mutating call of a real rotation vs five reads (full space with `FIELD_SLOW_TESTS=1`: 5,293 of 5,293 schedules pass on Windows; default run = a 1/24 sample; the harness's wall-clock bounds — reader join, writer park, the 5 s snapshot busy deadline — are 120-180 s, so a reader starved on a loaded host is not reported as `stuck` or `busy`); each rotation step placed independently before any read observation (full: 26,747 of 26,747 pass; default = a 1/8 sample of the three single-snapshot reads), with a negative control that emulates deciding the layout from separate stats and IS caught (full: 95 silent short chains + 242 false breaks; default = a 1/3 sample of one read); thread + process + CLI reader stress; readers during archival. A half-copied last line is re-read, not believed (`tests/test_ledger_rotation.py::test_torn_in_flight_last_line_is_reread_not_believed`, deterministic; the timing-based `test_reader_never_fails_on_append_in_flight` cannot fail on Windows, where such a line was never observed, and matters on Linux). Pre-C2 code (a rolled-back image, an old CLI) is NOT covered — see LIMITS |
| A second writer process does not fork the chain or lose an acknowledged event | **Enforced in code** | every write path takes `.<name>.lock` (msvcrt / flock) after the in-process lock and re-reads the files first. `test_second_writer_process_loses_no_acknowledged_event` (a `ledger append --path`-style process vs a service process appending and rotating: every ack from both present), `test_second_writer_size_mismatch`. Only writers running this code take the lock |
| Anchors taken before rotation keep verifying; an anchor inside an archived segment fails explicitly | **Enforced in code** | positions are global, resolved from one snapshot; `segment` is excluded from the signed bytes when absent. `test_real_scene4_anchor_signed_before_c2_still_verifies` (the real anchor signed 2026-08-10), `test_pre_rotation_anchor_still_verifies` (after 2 rotations), `test_signed_view_excludes_segment_when_none`, `test_anchor_inside_archived_segment_is_explicit_failure` (names segment and `archived_to`; the archived state is written by a test stand-in until retention apply exists), `test_write_anchor_during_rotation_never_zero`; an anchor in a live segment whose file is gone fails as missing, never passes (`tests/test_ledger_c2_hardening.py::test_an_anchor_in_a_missing_live_segment_fails_as_missing`) |
| `/health` answers from a cache: never locks, never walks the chain, and never re-counts for this process's own appends | **Enforced in code** | `test_health_is_cached_global_and_takes_no_lock` (answers while the writer lock and the read gate are both held); `tests/test_ledger_c2_hardening.py::test_health_out_of_band_recount_takes_no_lock_no_gate_and_no_pydantic` (another process wrote: /health answers in < 2 s with the new count while the writer lock AND the read gate are held, through exactly one `parse=False, open_only=True` snapshot and no pydantic parse); `test_health_does_not_recount_while_this_store_s_own_append_is_in_flight` (an append written and fsynced but not yet in the cache is recognised by its published disk key: no recount); `tests/test_ledger_c2_hardening.py::test_health_does_not_recount_during_the_append_that_creates_a_new_ledger` (the first append to a brand-new ledger creates the open segment, so its key is published as "any inode, size 0 or the line's size": /health between create and write, and between fsync and the cache update, answers from the cache with no recount); `test_ledger_latency_100k.py::test_health_is_o1_at_100k_events` (idle) and `test_health_stays_o1_at_100k_while_this_process_appends` (4 threads appending to the same store: 0 out-of-band recounts, p95 < 50 ms asserted; one run: p95 0.51 ms). Measured on a loaded shared Windows laptop at 100,000 events, idle, across the builder's and reviewers' runs: in-process max 0.2-6 ms, real HTTP p95 3-25 ms, HTTP max up to ~29 ms (J16 bound 50 ms; the tests assert in-process max and HTTP p95). Served at 100k with 4 HTTP clients appending, one run on the same laptop after this change: `/health` p95 41.9 ms, 22 of 594 samples over 50 ms, max 320 ms (the review measured p95 358-372 ms there before it) — so J16's 50 ms holds at p95 only narrowly under HTTP load on this host. Not re-measured on the GB10 (the review measured p95 82 ms there before the change) |
| `/health` and appends do not queue behind heavy reads | **Enforced in code** | the served app runs `/health` and `POST /events` on their own worker threads; `/verify`, `GET /events` and `/export` wait as queued work items (holding no thread) on a pool as wide as the read gate, and serialise their JSON there. `tests/test_ledger_c2_hardening.py::test_health_and_appends_do_not_wait_behind_queued_heavy_reads` (real uvicorn; the read gate is held while 60 `/verify` queue on it: every `/health` 200 < 2.0 s and every append 201 < 5.0 s, then all 60 reads answer ok once the gate opens — on the code before the lanes every `/health` and append timed out), `test_served_concurrency_uvicorn` (4 `/verify` loops, appends and two `POST /rotate` on a real server: every ack kept in order, no short or broken verify). What this does NOT remove: a parse that is RUNNING competes with the event loop for the GIL (see LIMITS). Other routes (`/rotate`, hold, retention) still use the shared pool |
| A busy ledger is never reported as tampered | **Enforced in code** | `test_busy_snapshot_is_never_reported_as_tampering`: `/verify` 200 `ok: false` `ledger busy: …`, `/events` and `/export` 503, CLI `BUSY —` exit 4, appends 201 |
| Nobody can rewrite history *at all* | **Declared only** | filesystem write access defeats append-only-ness; WORM storage + off-box (or public-chain) anchor placement is deployment responsibility |
| The rotation anchor proves a closed head to a third party | **Declared only** | the anchor key lives on the ledger host (`FIELD_LEDGER_ANCHOR_KEY`), so it is evidence only against someone without box access, and only if the returned `anchor` is shipped off-box |
| Per-event signatures: every event the ledger writes carries an Ed25519 `signature` over its hashed record when `FIELD_LEDGER_SIGN_KEY` is loaded; editing any field of a signed event fails `verify --event-pubkey` naming the index even after the chain is re-linked; a wrong key fails; pre-F2 history verifies with its unsigned count stated | **Enforced in code when the key is set** (the ledger's key: it proves the ledger wrote it; not yet armed on either estate — A7) | `LedgerStore._seal` signs after `make_event` hashes; `tests/test_event_signing_f2.py`: `test_key_loaded_every_append_is_signed_and_verifies`, `test_cli_verify_relinked_tamper_of_a_signed_event_fails_naming_the_index` (the anchor forgery test's stronger sibling: plain verify passes, `--event-pubkey` names index 1), `test_cli_verify_every_relinked_field_edit_of_a_signed_event_is_named`, `test_cli_verify_wrong_event_pubkey_exit_1_naming_index_0` (a stranger's key and the ANCHOR key both fail), `test_cli_verify_pre_f2_fixture_verifies_with_the_unsigned_count` (`signed 0 unsigned 5`), `test_cli_verify_mixed_history_reports_every_index`, `test_cli_verify_event_pubkey_across_rotation_closed_archived_and_genesis_modes` (rotation events signed too), `test_verify_export_passes_on_a_bundle_carrying_signed_events`, `test_anchor_key_is_never_used_for_events`. field-core: `packages/field-core/tests/test_event_signatures_f2.py` (hash unchanged by signing, the flag inside the hash, plain `verify_chain` blind to the re-link the signature catches). The honest limit is pinned: `test_cli_verify_a_stripped_signature_is_reported_at_the_tail_and_failed_elsewhere` |
| An unsigned append's JSON line is byte-identical to a pre-F2 line (no `signature`, no `signing_failed` key), and a pre-F2 line parses with its hash unchanged | **Enforced in code** | `test_no_key_appends_unsigned_with_exactly_the_pre_f2_keys_on_disk`, `test_unsigned_line_has_exactly_the_pre_f2_keys_and_signed_lines_no_extra_keys`; field-core `test_unsigned_event_json_has_no_signature_and_no_signing_failed_key`, `test_pre_f2_fixture_line_parses_unchanged_and_its_hash_is_unchanged`, `test_signed_line_round_trips` |
| Fail closed: with `FIELD_LEDGER_REQUIRE_SIGNING=1` and no key loaded, a start-type append is refused 503 (nothing written), a stop-type append succeeds stamped `signing_failed: true`; rotation, hold placement and retention apply are refused before anything is written or moved; a missing or bad key is never a process exit | **Enforced in code** (CI-proven fault path; off by default, armed at A9) | `LedgerStore._require_appendable` / `_seal`, `is_stop_type`; `test_require_signing_no_key_refuses_start_type_before_writing_anything` (delete the refusal and it fails), `test_require_signing_no_key_accepts_stop_types_stamped_signing_failed` (each stop type; the stamp is inside the hash), `test_is_stop_type_each_class` / `test_is_stop_type_near_misses_are_start_type` (`kill` without the dot, `kill.`, `lifecycle.decommission`), `test_require_signing_with_an_error_key_behaves_as_no_key`, `test_require_signing_off_with_an_error_key_appends_unsigned_with_no_flag`, `test_hold_rotation_and_retention_are_refused_before_writing_when_not_appendable`, `test_post_events_503_for_start_type_and_201_signing_failed_for_stop_type`, `test_served_app_builds_from_env_with_a_missing_key_never_a_process_exit`, `test_load_signing_config_never_raises_and_reports_each_state` (unset, blank, missing, directory, garbage, EC key, a public key), `test_health_*` (every field, `key_error` only on `error`); the CI script is proven against the real apps in `services/conformance-sentinel/tests/test_f2_signing_fault_script.py` (and shown to FAIL on a healthy ledger) |
| Caller authorship (F2b): an event appended by a service carries that service's `caller_id`, `caller_ts` and `caller_signature`, verifies under that service's recorded public key, and the claim is stored only after the ledger verified it — an unknown caller, an invalid signature, a `caller_ts` outside the 300 s / 60 s replay window, incomplete fields, or caller fields with no keyring configured are refused 403 with nothing written | **Enforced in code when the keyring is set** (GB10 only, arming step A7b; the callers' keys are on the box: evidence against actors without box access) | `CallerPolicy.check` before the writer lock, `LedgerStore.append_for_caller`; `tests/test_caller_signing_f2b.py`: `test_signed_caller_append_stored_and_verifies` (stored, inside the hash, under the ledger's signature, served verbatim; a re-linked `caller_id` edit fails both signatures), `test_ledger_client_signs_end_to_end_against_the_served_app`, `test_unknown_caller_403` (no PEM, a traversal-shaped id, a keyring file that is not an Ed25519 public key), `test_bad_signature_403` (another key, every covered field changed after signing, malformed), `test_stale_caller_ts_403` (both edges, a replayed body, the injectable clock), `test_no_keyring_but_caller_fields_403`, `test_incomplete_caller_fields_403`. field-core: `packages/field-core/tests/test_caller_signatures_f2b.py` (five covered keys, ledger-only fields not covered, the fields inside the hash and under the F2 signature; the client body unchanged with the env unset, signed with it set, unsigned with one warning and never an exception when the key does not load) |
| Fail closed on caller authorship: with `FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1` a start-type append without caller fields is refused 403 (nothing written), a stop-type one succeeds stamped `caller_unsigned: true` inside the hash; a stop-type append that PRESENTS a bad claim lands the same way with the claim dropped, never 403, while a start-type one with the same bad claim is 403; with the switch off a bad claim on a stop-type is 403 like any other; the ledger's own events (CLI append, hold, rotation, retention) are exempt | **Enforced in code** (off by default; armed LAST at A7b) | `test_require_caller_signature_start_type_unsigned_403`, `test_require_caller_signature_stop_type_unsigned_201_caller_unsigned_true` (the stamp is inside the hash: stripping it is a chain break), `test_require_caller_signature_stop_type_with_a_bad_claim_lands_unsigned_never_403` (wrong key, unknown caller, stale `caller_ts`, incomplete fields, no keyring — each against every stop type; none of the three fields stored; the reason logged; the same claim on a start-type is 403), `test_require_off_a_bad_claim_on_a_stop_type_is_403_like_any_other`, `test_ledger_own_events_are_exempt_from_require_caller_signature` |
| An append without caller fields stores none of `caller_id` / `caller_ts` / `caller_signature` / `caller_unsigned` (the line is still a pre-F2 line), and `/health` reports `caller_keyring`, `caller_keys`, `require_caller_signature` | **Enforced in code** | `test_unsigned_append_unchanged_when_env_unset_omitted_when_absent` (keyring on/off × ledger key on/off), `test_health_reports_caller_keyring_and_require`, `test_served_app_builds_the_policy_from_env_and_sees_a_key_imported_after_start`; field-core `test_unsigned_event_json_has_no_caller_keys`, `test_pre_f2_fixture_line_parses_unchanged_and_its_hash_is_unchanged` |
| `verify --caller-keyring` fails an unknown caller or an invalid caller signature naming the index, in every verify mode, and reports unsigned events without failing them | **Enforced in code** | `test_cli_verify_caller_keyring_reports_and_fails_correctly` (a re-linked payload edit, a re-attributed `caller_id`, a keyring missing a caller, a keyring with the wrong key, a non-key file, a non-directory ⇒ exit 2, a chain break first), `test_cli_verify_caller_keyring_with_event_pubkey_prints_both_lines_in_order`, `test_cli_verify_caller_keyring_pre_f2b_history_reports_all_unsigned`, `test_cli_verify_caller_keyring_across_rotation_closed_archived_and_genesis_modes`, `test_export_bundle_carries_caller_fields_verbatim_and_verifies` |
| `keys import-public` refuses anything but an Ed25519 public key (a private key is never echoed) and never overwrites | **Enforced in code** | `tools/tests/test_volume_admin.py`: `test_import_public_refuses_anything_but_an_ed25519_public_key_and_writes_nothing`, `test_import_public_never_overwrites`, `test_import_public_writes_the_re_encoded_key_never_a_trailing_private_block`, `test_import_public_refuses_a_bad_caller_id`, `test_import_public_writes_the_pem_0644_prints_the_fingerprint_and_the_ledger_keyring_reads_it` |
| Caller authorship on Fly | **Declared only** | a single container: every process can read every key, so a per-service key proves nothing there. Not deployed on Fly (`caller_keyring: off`). An export's `signature.json` signs the bundle (summary + chain_proof), not the events |
| Retention apply archives only committed closed segments that verify, oldest first, with the journal op before the move and the move outside the lock, never overwriting and never across filesystems; it never runs on a ledger whose live verify breaks, and a run refused part-way still ledgers what it archived | **Enforced in code** | `tests/test_ledger_c2_hardening.py`: `test_forged_archive_op_over_a_deleted_segment_is_a_break_and_apply_will_not_launder_it` (a live-verify break refuses the run before anything is written), `test_apply_refused_after_archiving_a_segment_still_ledgers_it` (a hold placed, or segment 2 damaged, after segment 1 was archived: the refusal still appends `ledger.retention.applied` naming segment 1 with an `error`, and no sidecar is left for segment 2), `test_a_hold_placed_after_the_sidecar_is_written_leaves_no_sidecar_behind`. `tests/test_ledger_retention.py`: `test_archival_keeps_live_verify_ok_and_sidecar_verifies_standalone` (verify ok, global length, `archived_segments == 2`, `/health` `earliest_live_index` 8, one `ledger.retention.applied`); `test_apply_never_archives_a_segment_that_does_not_verify`; `test_apply_refuses_when_the_journal_disagrees_with_the_rotation_event` (an edited journal entry is never copied into a sidecar); `test_apply_never_overwrites_an_existing_archive_file_or_sidecar`; `test_a_pending_move_never_overwrites_a_different_archive_file`; `test_journal_commit_precedes_the_move_and_the_move_runs_outside_the_lock`; `test_a_rotation_between_plan_and_successor_read_replans_instead_of_refusing` (a concurrent rotation is never reported as corruption); `test_apply_respects_age_and_prefix_and_is_idempotent` (a second apply writes no event); `test_archive_dir_rules` (inside the ledger dir, outside `FIELD_DATA_DIR`, another filesystem — simulated through the `st_dev` seam, not a real second volume); `test_windows_plain_handle_leaves_pending_move_without_duplicate` (Windows only: the file stays in place, no archive copy, the next apply completes it); `test_readers_during_rotate_and_real_retention_apply_never_see_a_short_ok_chain` |
| A process killed at a named step of retention apply never silently shortens the chain, and the next apply completes the archival; a process killed while placing or releasing a hold leaves the hold in force | **Enforced in code** (process kills at 4 archive and 2 hold steps) | `test_crash_at_each_archive_step_never_silent_and_next_apply_completes` (sidecar written / journal record torn / committed / moved: a fresh read is ok, changes no file and the live events are the acked suffix; the next apply leaves `pending_moves == []`, both segments archived and both sidecars verifying with the key); `test_crash_at_each_hold_step_leaves_the_hold_in_force`. There is no syscall-level sweep for archival (the rotation sweep covers rotation only), power loss is not tested, and a crash after a segment is moved but before the run ends leaves that archival in the journal and its sidecar but in no `ledger.retention.applied` event (live `verify` then checks that segment from its archive copy, `test_an_archival_whose_event_never_landed_is_verified_from_its_archive_copy`; a later run does NOT turn that byte evidence into event evidence, so removing that copy is a break for as long as the journal names the segment: `test_bytes_only_evidence_is_never_promoted_by_a_later_apply`) |
| An archived segment verifies standalone from its sidecar, naming GLOBAL indices; with the public key, its signed rotation anchor pins the head | **Enforced in code** — NARROWED | `verify_segment_file` / `ledger verify --path <archived file> [--pubkey]`: chain from the sidecar's `genesis_prev_hash`, count, head, `sha256` of the bytes; with `--pubkey` the anchor signature must verify and pin `head_hash`, `chain_length = end_index + 1` and the segment number; segment 1 must start at global 0 from the genesis hash (`test_archival_keeps_live_verify_ok_and_sidecar_verifies_standalone`, `test_sidecar_verify_negative_cases`; a segment rewritten inside itself with only the unsigned sha-256 updated fails on its head, with or without the key: `tests/test_ledger_c2_hardening.py::test_an_archived_segment_rewritten_inside_itself_fails_its_sidecar_head`; a sidecar copied beside another file name fails: `test_a_sidecar_copied_beside_another_file_name_fails`). NOT proven: without `--pubkey` the sidecar is its own unsigned claim (rewriting the file and the sidecar together verifies — the test pins this); with it, the START of segment n > 1 is pinned only by segment n-1's signed head, so verify archived segments in order |
| A legal hold blocks retention apply, including one placed while an apply is running; blank names are refused | **Enforced in code** | `test_hold_blocks_apply_exit_4_listing_unchanged` (CLI exit 4, ledger directory listing and the archive dir unchanged), `test_hold_is_rechecked_under_the_writer_lock_before_the_journal_commit`, `test_blank_hold_name_refused` (CLI exit 2, HTTP 422, no file, no event), `test_served_hold_and_retention_routes` (423 / 409), `test_cli_hold_and_retention_delegate_to_the_served_routes` |
| The hold marker binds anyone who can touch the ledger's files | **Declared only** | it is a file: anyone with write access to the ledger directory can delete it, and `placed_by` / `by` are recorded strings, not authenticated identities |
| The estate retention policy is checked against every registered manifest; a check that could not run is never ok | **Enforced in code** (reporting) | `test_retention_check_estate_365_vs_manifest_2555_exit_3` (offending agent named, exit 3; 2555 ⇒ exit 0), `test_retention_check_agent_without_manifest_ref_skipped` (counted, not unresolvable), `test_retention_check_unresolvable_ref_listed_exit_3` (missing and invalid, sorted), `test_retention_check_without_a_usable_estate_policy_exits_3` (unset, blank, not an integer, 0), `test_retention_check_registry_disabled_or_down_is_unavailable_never_ok` (an injected test store has no registry and makes no network call; the self-built app builds a `RegistryClient` per request); ledger state that cannot be read makes the check `unavailable` with every ledger field null, never "no hold, 1 segment" (`tests/test_ledger_c2_hardening.py::test_retention_check_never_invents_ledger_state_it_could_not_read`). Lifecycle and the board pack consume it (their READMEs) |
| X4 direction 1 appends exactly one signed `anchor.remote{estate: fly}` per tick, only from a head it read from Fly's `/ledger/health`, through the served route with the perimeter header; a failed read appends nothing | **Enforced in code** | `tests/test_witness.py` against a stub Fly (httpx `MockTransport`, https) and the real ledger app on uvicorn: `test_a_tick_appends_exactly_one_signed_anchor_remote_through_the_served_route` (exact payload keys, values, observer, fingerprint, signature verifies; one GET, no `x-field-auth` sent to Fly), `test_the_local_append_carries_the_perimeter_header`, `test_a_failed_fly_read_appends_nothing` (down, timeout, 503, a redirect to a host serving a valid head, not JSON, a boolean count, upper-case hex, a negative count, a duplicate `head_hash` key), `test_the_fly_client_never_follows_redirects_and_has_a_timeout`, `test_fly_url_must_be_https`, `test_cli_once_exit_codes` |
| A missing or unusable anchor key appends nothing, sends nothing and never ends the witness; the key is re-read every tick | **Enforced in code** | `test_no_usable_key_appends_nothing_sends_nothing_and_the_loop_keeps_running` (unset, missing, garbage, an EC key: tick 1 appends nothing and makes no Fly request, the key is fixed, tick 2 appends one), `test_a_raising_tick_does_not_end_the_loop` (first tick at start, `run_loop`) |
| X4 direction 2 is sent only with `FIELD_WITNESS_FLY_SECRET_FILE`, with that secret and a signed body; neither secret reaches a log | **Enforced in code** — NOT live until D5 | `test_direction_2_is_off_by_default_with_one_line_per_tick`, `test_direction_2_posts_the_local_head_signed_with_the_fly_secret` (the Fly secret, never the local one; `length`/`head_hash` = the local head after direction 1), `test_direction_2_with_an_unusable_secret_file_sends_nothing`, `test_secrets_never_reach_the_logs_even_when_a_refusal_echoes_them` (a refusal body that echoes the header is logged redacted; caplog, CLI stderr), `test_a_refusal_echo_straddling_the_log_cut_leaks_no_prefix_of_the_fly_secret` and `…_of_the_local_secret` (an echo that crosses the 200-character cut, from Fly and from the local ledger: no 6+ character prefix of either secret is logged) |
| `verify-witness` checks every `anchor.remote` of an estate IN ITS SOURCE — `/events` of the witnessing ledger serves its LIVE segments only, so an anchor in an ARCHIVED segment of the witnessing ledger (even one that would fail) is not loaded and not counted (LIMITS) — and can fail; at least one anchor of length >= 1 must hold | **Enforced in code** (for the anchors in the source) | `test_every_anchor_holds_across_a_rotated_ledger` (anchors before and after a rotation, 2 segments, JSON array and JSONL, 3 signatures), `test_one_edited_head_hash_fails_naming_it`, `test_a_length_beyond_the_local_chain_is_a_future_head`, `test_an_archived_index_is_an_explicit_failure`, `test_zero_anchors_is_nothing_witnessed`, `test_a_bad_signature_with_pubkey_fails` (an edited `observed_at` passes WITHOUT `--pubkey` and fails with it; another key; unsigned), `test_a_valid_signature_with_a_wrong_fingerprint_fails`, `test_duplicate_keys_are_refused`, `test_a_local_chain_that_does_not_verify_fails_before_any_anchor`, `test_an_anchor_past_the_verified_length_is_never_checked_against_unverified_events` (an event appended between the chain verification and the lookup is not trusted), `test_a_malformed_anchor_fails_by_name` (length a string, a boolean, negative; head_hash not hex, missing), `test_a_zero_length_anchor_holds_only_at_the_genesis_hash`, `test_length_zero_anchors_alone_are_nothing_witnessed` (an unrelated ledger; unsigned, and signed with `--pubkey`), `test_an_index_missing_from_the_live_chain_fails_even_without_a_verified_length`, `test_verify_witness_over_events_url` (and a secret refused over http), `test_verify_witness_never_follows_a_redirect_carrying_the_secret` (a 302 to a host serving holding anchors: exit 2, the target receives no request), `test_no_served_route_signs_anything` |
| An `anchor.remote{estate: fly}` proves Fly's head | **Declared only** — NARROWED | it proves what the GB10 witness read from Fly's open `/health` over TLS at `observed_at`, signed with the GB10's on-box anchor key. Fly itself did not sign it, and `observer` is a signed claim by that same key, not an authenticated identity |
| Retention periods in manifests are enforced per agent | **Declared only — not possible by design** | retention is estate-level: one shared chain, no per-agent purge. The check REPORTS a manifest that declares more than the estate keeps; nothing archives or refuses because of it, and `retention apply --days` is not compared with `FIELD_LEDGER_RETENTION_DAYS` |

## LIMITS

- Writers coordinate through `.<name>.lock` beside the open segment, so two
  `LedgerStore` instances or processes on one file no longer fork the chain.
  Only code from C2 on takes that lock: a pre-C2 writer (a rolled-back image,
  an old CLI) ignores it and can still fork the chain. Two instances on one
  path must never nest writes in the SAME thread (the inner write waits 30 s
  for the outer's lock, then fails `ledger busy`).
- **Windows: a foreign plain handle blocks rotation.** Any process holding the
  open segment without FILE_SHARE_DELETE (an editor, an AV or backup scanner,
  `Get-Content -Wait`, a Python tool using plain `open()` — `field
  verify-chain` included, while it reads — pre-C2 ledger code) makes the
  rename fail: rotation retries 5 × 100 ms, then answers 503 /
  exit 4 with `rotate-intent` + `rotate-abort` journaled and nothing renamed;
  appends and `/health` keep working (`test_foreign_plain_handle_rotation_503_nothing_renamed`).
  The refusal refreshes only the journal part of the writer's caches (it no
  longer re-parses the whole open segment under both writer locks, which the
  review measured at 3.9-4.3 s, with one append stalled ~4 s, at 100k events:
  `tests/test_ledger_c2_hardening.py::test_a_refused_rename_does_not_re_parse_the_open_segment`).
  Re-measured on the same laptop at 100k with a real server, appends and
  `/health` every 100 ms: the 503 came back in 0.46-2.07 s over five runs,
  with no append over 1.5 s and no `/health` over 0.33 s inside the rotation
  window (one run of the previous code on the same host that day: 1.90 s).
  Two of those runs also had appends (3 and 5) and `/health` samples (7 and
  11) time out OUTSIDE the rotation window, which this probe did not explain;
  three timeline runs showed only a slow first request after server start.
  Linux renames over open handles (the holder keeps reading its old file).
- **Pre-C2 readers must not read a rotating or rotated ledger.** Old code
  (a rolled-back image, an old CLI on PATH) knows nothing of segments: during
  each rename window it sees an empty file that verifies ok (the build spec lab
  measured this in 18 % of tight-loop reads under continuous rotation), and
  after a rotation it reports `link break at index 0`. No new code can fix old
  binaries. `field verify-chain` (single-file by design) prints a stderr note
  on a rotated open segment.
- The segments journal is not tamper-evident by itself (see the journal row);
  its fields are trusted only as far as the hash-chained rotation event of
  the following live segment confirms them, and each `archive` record only as
  far as its own evidence confirms it: its bytes still in the ledger
  directory, a live `ledger.retention.applied` event naming that segment with
  the journaled sha-256, or its archive copy. Whoever can append to the
  journal AND post a retention event naming the segment and digest hides a
  deleted segment; an appended `archive` line over INTACT bytes verifies and
  takes that segment's events out of `/events` (journal row, NOT detected).
  `ledger verify --path events-<n>.jsonl` checks a closed segment (or a
  pending move, or a pending rotation's renamed file) against the journal's
  `genesis_prev_hash` / `head_hash` alone.
- Retention apply verifies the whole live chain once per run before it
  commits anything (one full parse behind the read gate, seconds at 100k
  events), so a ledger with any break — anywhere — is not archived until an
  operator resolves it. Removing the archive copy of a segment whose
  `ledger.retention.applied` event never landed (a killed run) is a break,
  and stays one: a later run's event never vouches for a segment it did not
  archive itself unless an earlier live event already named it.
- A store cannot be opened on an open segment with a line that does not
  parse (as before C2: `test_torn_last_line_raises_as_today`), so a ledger
  process restarted on such a file does not start (reads get no answer). A
  running process reports the line as a break on `/verify` (HTTP 200). It
  refuses appends (500) when the edit changed the open segment's size; an
  in-place overwrite of the same byte length is not noticed by the append
  path, which then chains new events past the bad line (`/verify` still
  reports the break at its index). A closed segment with such a line is a
  break on any store. Plain `verify` does not see a deleted TAIL record at all — only the
  anchor comparison does.
- Back up the ledger directory, the archive directory, the journal and
  `legal_hold.json` together: every `events-<n>.jsonl`, the open segment,
  `events.segments.journal`, every archived segment with its sidecar (a
  segment without the journal, or the journal without its live segments, is
  reported as a break; an archived file without its sidecar cannot be verified
  standalone).
- **Retention apply moves, it never deletes and never copies.** The archive
  directory must be on the ledger's filesystem (a second volume is refused),
  so archival frees nothing on that volume. `--days` is the operator's choice
  and is not compared with `FIELD_LEDGER_RETENTION_DAYS`; deleting or shipping
  archived files is outside the platform.
- A segment whose rename is refused (Windows: another process holds the file
  with a plain handle) is archived in the journal but still in the live
  directory — a pending move, listed in `pending_moves` and in
  `/retention/check`, completed by the next apply. If a DIFFERENT file already
  sits at its archive path, the move stays pending forever and nothing is
  overwritten: resolve the conflict by hand.
- A crash between writing a sidecar and the journal commit leaves an
  uncommitted sidecar. The next apply by the same `--operator` accepts it
  (identical content); another operator is refused until that sidecar is
  removed (it is not referenced by the journal). A refusal (legal hold,
  corrupt journal) at that point removes the sidecar this run wrote; only a
  killed process leaves one.
- `retention check` reads the registry from where the LEDGER runs
  (`FIELD_REGISTRY_URL`, `FIELD_MANIFEST_DIR` in the ledger container) and
  resolves only filesystem manifest refs (B0: no URL refs). A ledger app built
  around an injected store (every test stack) has no registry and answers
  `unavailable`.
- Retention apply and the hold have been tested on Windows only (Python 3.14),
  not on Linux, not at 100k events, and not against a real registry.
- The rotation signing key is on the ledger host: its anchor is evidence
  only against actors without box access, and only once shipped off-box.
- **Per-event signatures (F2) are the ledger's, on-box.** They prove the
  ledger process holding `FIELD_LEDGER_SIGN_KEY` wrote a record, not who
  asked it to, and only against actors without box access (the key holder
  can re-sign anything). Unsigned events are never a failure of
  `verify --event-pubkey` — pre-F2 history and `signing_failed` stop-type
  events are legal — so a replaced TAIL event with its signature dropped is
  reported (`first_unsigned_after_signed`, the unsigned count), not failed;
  a dropped signature anywhere else fails at the next signed event. Served
  `GET /verify` checks the chain only. The A9 fault path is CI-proven, not
  live-verified: on a live estate an unreadable key with
  `FIELD_LEDGER_REQUIRE_SIGNING=1` BLOCKs every agent's `/check`.
- **Caller signatures (F2b) are on-box too, and GB10-only.** A stored
  `caller_signature` proves the service holding that key asked for the
  append, not that the append was justified; root on the GB10 holds every
  service's key. The replay window (300 s back, 60 s ahead) bounds a
  replayed body, it does not detect a duplicate inside the window, and it is
  not re-checked by `verify`. A service whose key did not load appends
  UNSIGNED with one warning until `FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1`
  is armed, and under it a stop-type append still lands (stamped
  `caller_unsigned`; a bad claim on it is dropped, not refused), so `caller_unsigned`'s count and
  `first_caller_unsigned_after_signed` are what the operator watches, as with
  F2. The offline `ledger append` on the box and the ledger's own events
  never carry caller fields. A ledger image without F2b drops the claim
  silently (the body's extra keys are ignored). Fly: not deployed — every
  process in its one container can read every key.
- **X4 witnessing.** GB10 down ⇒ both directions stop; Fly never initiates without D6.
  Direction 2 (the GB10 head onto Fly's ledger) is not live until D5; until
  then only Fly's head is witnessed, on the GB10. The witness key IS the
  on-box anchor key (`/data/keys/ledger-anchor.pem`, read-only into the
  witness): its signatures are tamper-evidence only against actors without
  GB10 box access. An `anchor.remote` proves what the GB10 read from Fly's
  open `/health` over TLS at `observed_at` — Fly itself did not sign it, so a
  GB10 box holder can forge one, and whoever answers as Fly's origin with a
  valid certificate is believed. Any perimeter holder can append an
  `anchor.remote` event: only `verify-witness --pubkey` tells a signed one from
  a lookalike, and the lifecycle freshness finding counts events by ledger
  `ts` without checking signatures. `verify-witness` checks the live chain it
  is pointed at; anchors held in an ARCHIVED segment of the witnessing ledger
  are not served by `/events` and so are not loaded: one that would FAIL is
  silently absent from the `N of N`, and the run can still exit 0 on the rest. A tick is not atomic
  across estates: Fly's head can move between the read and the append.
- Process kills are tested at every rotation step; power loss is not, and
  Windows cannot fsync a directory. The target-absent check before each rename
  is not atomic against a foreign process creating `events-<n>.jsonl` in
  between (no `RENAME_NOREPLACE`).
- Readers never lock, but at most one full-chain parse runs per process at a
  time (`FIELD_LEDGER_READ_CONCURRENCY`, default 1): concurrent `/verify`,
  `/events`, `/export` queue. At 100k events on the 20-core GB10 the build spec
  measured ~4.3 s per request with 4 concurrent `/verify` — above a 5 s client
  timeout for the second and later. Under extreme rotation rates a read can
  answer `ledger busy` (never ok, never tampered); callers retry. The gate is
  also the ledger's memory bound: the review measured peak RSS at 100k events
  of ~320-420 MB with the default of 1, and ~1.9-2.1 GB with the gate off and
  8 concurrent readers. The Fly machine has 2 GB for 13 services plus Caddy:
  do not raise `FIELD_LEDGER_READ_CONCURRENCY` there
  (`tests/test_ledger_c2_hardening.py::test_heavy_read_gate_width` pins the
  default of 1). Queued reads hold no worker thread and never make `/health`
  or appends wait for one (the lanes row); a client that gives up does not
  remove its queued read. A read that is RUNNING is CPU-bound Python in the
  same process as the event loop, so it still slows `/health` and appends
  through the GIL: on this loaded Windows laptop, with a 20,000-event
  `/verify` parsing, `/health` took 0.04-0.7 s per request, and one sample
  took 2.1 s (over the sentinel's 2.0 s) inside a 636-test pytest process.
  At 100k events, 60 concurrent `/verify` against a real server (one alone
  2.6 s), one run after the lanes: 22 of 22 `/health` under 2.0 s (p95 296 ms,
  max 752 ms) and 22 of 22 appends under 5.0 s (p95 722 ms, max 3.8 s); the
  review measured 3 of 3 of each timing out before them. The GB10 was not
  re-measured.
- `/health` `event_count` counts the live segments plus the archived range
  from the journal; it is a cache refreshed by this process's writes and by
  a lock-free recount of the open segment when another process wrote. This
  process's own append in flight is not "another process" (its disk key is
  published before the write); a rotation or archival in this process can
  still cause one recount per disk key.
- The served app finishes a crashed rotation at startup only if one is
  pending, and a ledger that needs no reconcile is not written
  (`tests/test_ledger_c2_hardening.py::test_served_startup_never_writes_a_ledger_that_needs_no_reconcile`,
  on the pre-C2 shape with no lock file). If reconcile refuses, the service
  still starts: `/health` 200, `/verify` reports the break, writes answer 500
  (`test_served_startup_with_a_rotation_it_cannot_reconcile_still_serves`).
- Latency (build spec §6.5, 100k events, `FIELD_SLOW_TESTS=1`) measured on this
  build on a shared Windows laptop: `/health` during `/verify` max 0.64 s;
  append with 4 `/verify` in flight max 2.76 s (the spec lab measured 0.77 s
  on Windows); during a rotation of the 100k segment, append max 1.09 s and
  `/health` max 0.52 s; the rotation answered 200 in 2.1 s. The spec requires
  the pass on the 20-core Linux shape, which this build has NOT been measured
  on.
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
