# Operator key layer: declared limits

Three limits of the operator-key layer that the code states but no runbook
did (card C-46; reviewer cards C-20 and C-34). Each is a documented limit, not a
defect, and each cites the line that says so. Line numbers are for main at the
time of writing; re-grep the quoted phrase if they have moved.

## 1. Retired-key memory: in process memory, per registry path, capped

What it does: when a load of the operators file at a higher generation removes
a key hash, the verifier remembers that hash and refuses it if it comes back in
a file whose generation is not above the one that removed it (a restored
backup, a stale `.prev`). It learns a hash only from a higher-generation load
that LACKS it (`packages/field-core/src/field_core/operator_auth.py:1251-1256`);
a higher file that still carries the hash retires nothing.

The limits:
- The memory is in process memory only: "Memory resets on a process restart"
  (`operator_auth.py:1212`). It is also kept per registry path (`os.path.abspath`,
  `operator_auth.py:1243`), and each service that loads the file has its own
  (`packages/field-core/tests/test_operator_auth_format2.py:808`, test
  `test_retired_memory_is_per_process_and_per_path`).
- It learns only from loads this process makes.
- It is capped at `MAX_RETIRED_HASHES = 4096` (`operator_auth.py:1218`); when
  full, the oldest generations are dropped (`operator_auth.py:1258-1260`). The
  eviction is silent: no log line and no counter. Eviction removes the hash
  from the retired table only. In a running process a stale file BELOW the
  highest generation seen is still refused for every hash the highest file
  lacks (`operator_auth.py:1268-1269`, the below-high-water rule), evicted or
  not; an evicted hash matches again only in a file at or above the highest
  generation seen, or after a restart. The set of sightings that feeds the
  `operator_retired_hash_seen` counter and its ERROR log stops growing at the
  same cap (`operator_auth.py:1273`), so after that those two stop reporting
  new sightings while refusal of the hashes still held in memory continues.

Consequence: after a service restarts, restoring a stale `operators.json.prev`
that still holds a retired key makes that key match again until a load at a
higher generation that lacks it is seen. The restored file loads as a normal
file. A restart is what clears the high-water mark too; filling the table
alone does not let a stale lower-generation file back in a running process.

What to do: do not restore a `.prev` of the operators file after a key has been
retired unless the restored generation is the intended one. After any such
restore, check with the verify-hash route (section 3) that the retired key's
hash is not `matchable_now`, and run the check against EVERY service that loads
the file, not one.

## 2. Observer memory is per process: a restart records `startup: true`

What it does: the ledger's operator observer writes an event per service at
its first observation (`"startup": true`) and one each time the observed value
changes (`services/sealed-ledger/src/sealed_ledger/operator_observer.py:13`).

The limit: "first observation" means first for this ledger process. The
previous values live in the observer's own dictionaries.

False alarm: after the ledger process restarts, the mode and registry events
record `startup: true` again for every service, whether or not anything changed
(the previous-value variable is `previous` at `operator_observer.py:452` and
`:502`; `:486` uses a precomputed `startup`). The break-glass and retired-hash
events write a startup row only when the value is non-zero (`previous_bg is
None and any(bg)` at `:406`; `previous_n is None and n > 0` at `:463`).

Missed alarm (the half that matters): a disarm, a downgrade, a generation
decrease or a break-glass key change that happens while the ledger is down is
recorded only as `startup: true`, or not at all. The generation-decrease event
needs a previous value (`previous is not None and gen < previous`,
`operator_observer.py:395`) and `sealed_key_changed` is
`previous is not None and ...` (`:450`), so neither fires on a first
observation. After any ledger restart, compare the startup values with the
last rows written before the restart, by hand.

The observer also writes at most `MAX_WITNESS_ROWS = 256` rows per event
(`operator_observer.py:113` and `:196`); rows beyond that are dropped without
a marker.

## 3. `/operator/verify-hash` is a hash-match oracle behind one secret

What it does: `POST /operator/verify-hash` takes a key hash (never a key) and
says whether that hash is the named row's current or next key and whether it
would authenticate now (`packages/field-core/src/field_core/operator_health.py:57-63`,
answer built at `:467-500`). The answer also carries the registry format, its
generation and a prefix of the registry file's sha256, so a holder of the
secret learns those too.

What is enforced at the edge: both shipped proxy configs refuse this route and
`/operator/rotation-state` (403, never proxied) unless the request comes from
the proxy's own loopback with no forwarding hop (`integration/demo/Caddyfile:18-40`,
`integration/fly/Caddyfile:21-35`), and CI pins that
(`.github/workflows/ci.yml:174`, `:273`, `:505`).

What is not: on the compose network the service ports are reachable without the
proxy, so a holder of the perimeter secret on that network can call the route
directly (card C-48; a second, internal-only secret for it is proposed in card
C-54 and is not built). The route exists only when the operator layer is not
off and a perimeter secret is configured (`internal_routes_enabled`,
`operator_health.py:452-456`); there is no further check and I found no rate
limit (handler `operator_health.py:693-702`: secret gate, body cap, answer).
A holder of the secret can therefore test candidate hashes against any row
except the break-glass identity, which is refused (403).

How to call it (the shape sections 1 and 3 refer to): send
`POST <service>/operator/verify-hash` with the header `x-field-auth: <the
perimeter secret>` and a body of exactly
`{"operator_id": "<id>", "key_sha256": "<64 lower-case hex>"}`, from the
service's own network position (the shipped edges refuse it from elsewhere,
above). The answer names `matched` (`current`, `next` or `none`),
`matchable_now`, `retired`, and the registry format, generation and file hash
prefix (`operator_health.py:467-483`). It is a 404 when the operator layer is
off or no perimeter secret is set, and a body with any other field is a 422.
Never put a key in the body, only its hash.

Record: a question about a non-break-glass row writes no ledger event and
counts as no refusal (`operator_health.py:57-63`); I did not check what the
service's ordinary request log or the edge log keep. A break-glass question
increments `breakglass_attempt_count` (`operator_health.py:496`, `:503`),
which the observer ledgers.

Assumption, not a control: guessing a key through the oracle is impractical
only while keys are high-entropy. Keys made by `tools/operator_keygen.py`
are `fok_` plus 32 random bytes (`operator_keygen.py:119`), but the registry
side checks only a character pattern with a length of 1 to 256
(`_KEY_RE`, `operator_auth.py:87`), so there is no entropy or useful minimum
length. A hand-made or short key is not protected by this argument.
