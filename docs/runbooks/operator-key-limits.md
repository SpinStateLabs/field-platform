# Operator key layer: declared limits

Three limits of the operator-key layer that the code states but no runbook
did (card C-46; reviewer cards C-20 and C-34). Each is a documented limit, not a
defect, and each cites the line that says so. Line numbers are for main at the
time of writing; re-grep the quoted phrase if they have moved.

## 1. Retired-key memory resets on a restart

What it does: when a load of the operators file at a higher generation removes
a key hash, the verifier remembers that hash and refuses it if it comes back in
a file whose generation is not above the one that removed it (a restored
backup, a stale `.prev`).

The limit: that memory is in process memory only. The comment says it:
"Memory resets on a process restart" (`packages/field-core/src/field_core/operator_auth.py:1212`).
It also learns only from loads this process makes, and the table is capped at
`MAX_RETIRED_HASHES = 4096` (`operator_auth.py:1218`; the oldest generations are
dropped first, `operator_auth.py:1258-1260`).

Consequence: after a service restarts, restoring a stale `operators.json.prev`
that still holds a retired key makes that key match again until a load at a
higher generation is seen. The restored file loads as a normal file.

What to do: do not restore a `.prev` of the operators file after a key has been
retired unless the restored generation is the intended one; after any such
restore, confirm with the verify-hash route (section 3) that the retired key's
hash is no longer `matchable_now`.

## 2. Observer memory is per process, so a restart records `startup: true`

What it does: the ledger's operator observer writes one event per service at
its first observation (`"startup": true`) and one each time the observed value
changes (`services/sealed-ledger/src/sealed_ledger/operator_observer.py:13`).

The limit: "first observation" means first for this ledger process. The
previous values live in the observer's own dictionaries, so after the ledger
process restarts every service records `startup: true` again, whether or not
anything changed (the field is `previous is None` at
`operator_observer.py:411`, `:452`, `:466` and `:502`, and `startup` at `:486`).
The observer also writes at most `MAX_WITNESS_ROWS = 256` rows per event
(`operator_observer.py:113` and `:196`); rows beyond that are dropped without
a marker.

Consequence: a `startup: true` event is not by itself evidence of a disarm or
a downgrade. Read the `previous_*` fields: null on a restart, populated on a
change.

## 3. `/operator/verify-hash` is a hash-match oracle behind one secret

What it does: `POST /operator/verify-hash` takes a key hash (never a key) and
says whether that hash is the named row's current or next key and whether it
would authenticate now (`packages/field-core/src/field_core/operator_health.py:57-63`,
answer built at `:467-500`).

The limit: the route is reachable with the perimeter secret alone. It exists
only when the operator layer is not off and a perimeter secret is configured
(`internal_routes_enabled`, `operator_health.py:452-456`); there is no further
check. A holder of that secret can test candidate hashes against any row except
the break-glass identity, which is refused (403, counted as a break-glass
attempt). A key hash is a SHA-256 of a high-entropy key, so this is not a
practical way to recover a key, but it does confirm a hash guess. The route is
never ledgered and never counted as a refusal (`operator_health.py:57-63`), so
its use leaves no record.

Consequence: treat the perimeter secret as able to ask this question. Keep the
route off the public edge. A second, internal-only secret for it is proposed in
card C-54 and is not built.
