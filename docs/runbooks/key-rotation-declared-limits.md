# Key rotation: declared limits (read before acting on a rotation incident)

Three limits of the operator-key layer are Declared, not enforced. Each is a
fact about the code on `main`, with its source line. Nothing here changes
behaviour; it tells an operator what the layer will NOT do for them.
Source: reviewer findings C-20 f2, C-20 f3 and C-34 p2 f2.

## 1. The retired-hash memory resets on restart

**What happens.** A verifier refuses a key hash that a LATER generation of the
operators file removed, if that hash comes back in a file at or below the
generation that removed it (a restored backup, a stale `.prev`). That memory is
held per process and per registry path, and it resets when the process
restarts (`packages/field-core/src/field_core/operator_auth.py:1212`, "Memory
resets on a process restart (Declared, design section 11 row 10)").

**Consequence.** If a service restarts and then loads a stale operators file
(for example a `.prev` copied back by hand), the retired key is accepted again:
the new process has never seen the higher generation. The same comment
(`operator_auth.py:1213-1215`) says the memory learns only from loads this
process makes, so a generation that was live only between two loads is never
seen.

**What to do.**
- Never copy a `.prev` or a backup over a live operators file as a recovery step.
  The rotator writes a NEW generation above every generation ever issued; use
  that path.
- After any restore of the operators file, treat every key retired since that
  backup as live again: rotate the affected identities.

## 2. Observer memory is per process: a restart records `startup: true`

**What happens.** The sealed-ledger's operator observer writes one
`operator.mode_changed` and one `operator.registry_changed` event per service at
its first observation, carrying `startup: true`, and another when the observed
value differs from the last recorded one
(`services/sealed-ledger/src/sealed_ledger/operator_observer.py:11-14`). The
"last recorded" state is held in the observer process; `startup` is true when
there is none (for example `operator_observer.py:411`, `:452`, `:466`).

**Consequence.** After a ledger restart the observer re-records every service
as `startup: true`, even when nothing changed while it was down. A change made
WHILE the observer was down is therefore indistinguishable, in the ledger, from
a clean first observation: the event shows the new value with
`previous_*: null`, not a change from the old one. A `startup: true` event is not
by itself a sign of a change, and its absence is not a sign of no change.

**What to do.** When reading these events after a ledger restart, compare the
registry hash and generation against the rotator's own record (the journal and
status file under the rotation state directory) rather than trusting the
"changed" flag.

## 3. `/operator/verify-hash` is a hash-match oracle behind the perimeter secret

**What happens.** `POST /operator/verify-hash` takes a key HASH and answers,
for the named row, whether that hash is the CURRENT or NEXT key and whether it
would authenticate now (`packages/field-core/src/field_core/operator_health.py:57-62`;
answer built at `:467-504`). It is "never ledgered, never counted as a refusal"
(`operator_health.py:484`).

**Consequence.** Anyone who holds the perimeter secret and can reach the route
can test candidate hashes against an identity, without leaving a refusal count
or a ledger record. That is the route's purpose (the rotator uses it at design
steps 5, 9b and 10), and the only gate is the perimeter secret: the route
answers 404 when the operator layer is OFF or no perimeter secret is set
(`operator_health.py:452-460`, `:694-695`). The break-glass identity is never
answered (403, counted as a break-glass attempt, `:495-497`). It answers about a
hash, never a key, and a key is 256-bit random, so the oracle does not let a
caller recover a key; it confirms a hash a caller already has.

**What to do.** Treat the perimeter secret as the only control on this route:
keep it off any host that is not an operator host, and rotate it if it is
exposed. Do not rely on the refusal count or the ledger to notice use of this
route; neither sees it.

## Confidence

Each section quotes or points to the source lines above, read on `main` when
this was written. HIGH for what the code does at those lines. The line numbers
move with the files: re-check them before relying on a number.
