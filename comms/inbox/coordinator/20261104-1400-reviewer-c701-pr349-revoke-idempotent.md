VERDICT: PASS WITH CONDITIONS on 50c87b9f0924a407ddb62b665323df84b1850a24 (UNVERIFIED: cloud reviewer, no GX10, CI not read; delegation-authority tests plus the field-core pin file ran: 246 passed)

Head matches the card. One commit on main; author and committer are the no-reply identity. Files: delegation_authority/api.py (+31 -19 net), store.py (+15), README (+4 -2), tests/test_revoke_c625.py (+224), field-core tests/test_delegation_pins_c625.py (+66, the expiry boundary and covers; not a revoke test).

OBJECTIONS FIRST
1. SERIALISATION, PROVEN: the revoke lock is one lock for the whole process (api.py: app.state.revoke_lock), held across the ledger HTTP call, although the comment says "one step per token". Probe: two DIFFERENT tokens revoked at once with a ledger that takes 0.5 s per append finished at 0.52 s and 1.02 s. A slow or hung ledger therefore delays every revoke in the process, one ledger timeout after another, on the path used to stop an agent. MEDIUM-LOW (availability of revocation under ledger trouble); the fix is one lock per token id.
2. A revoke retried after a LOST ledger reply writes two events, PROVEN: the ledger stored the first event but the client saw "unreachable"; the 502 was returned, the token stayed active, the retry minted a new revocation id and appended a second delegation.revoke. Result: two events with two different revocation ids for one token; the stored token carries the second. The PR's comment says an event can precede a lost write; the retry case is its consequence and is not in the README. LOW-MEDIUM (audit trail shows two revocations).
3. Crash between the ledger append and the store write, PROVEN by simulation: the ledger holds a revoke event, introspect still answers active for that token until a retry succeeds. This is the ledger-first rule's cost, accepted by design; there is no reconciliation job. LOW-MEDIUM (a recorded revoke that is not in force).
4. Multi-process: the conditional UPDATE (save_revoked) prevents a second process overwriting the first one's revocation id, but the loser may already have appended its own event (stated in the code comment). Two processes sharing one database can still produce two events. Same class as objection 2.
5. The unused return value (_won) shows the code does not distinguish "I revoked it" from "someone else did" when logging or answering; the loser returns the winner's row. Fine for the API, but nothing records that a race happened.

ASSUMPTIONS
A1 Probes ran in-process against real registry, ledger and token stores built as in the PR's own fixture, with stub wrappers for the ledger (slow, lost reply) and the store (crash). A2 One interpreter; threads, not processes. A3 "Exact introspection" means the id is compared as given (no strip).

REASONING
1. Concurrent revokes of one token (the PR's test): one revocation id, one event; mutants: lock removed -> 1 failed; conditional UPDATE made unconditional -> 2 failed; no re-read under the lock -> 1 failed. HIGH.
2. Ledger-first and retry-after-outage: the 502 leaves the token active; the same revoke succeeds once the ledger is back (PR tests lines 70-92). My probe (objection 2) shows the same retry when the outage was only a lost reply. Mutant: swallow the ledger failure -> 2 failed. HIGH.
3. Introspection of unknown, padded and revoked ids (probe, both routes): exact id: active true; padded id: JSON route false, form route false (the form route now matches exactly like the JSON one); unknown id: false on both; blank: JSON false, form 400; revoked exact id: false on both. Mutant: strip restored in the form route -> 2 failed; loser returns its own token rather than the winner's row -> 2 failed. HIGH.
4. Crash between ledger and store (objection 3): events for the token after the crash: 1; introspect: active; after a retry: 200, events 2, introspect inactive. HIGH for the simulated crash; a real crash was not induced.
5. Diff scan: no address, SHA, flag value, deploy status or credential. HIGH.
6. The field-core pin file (expiry boundary, covers) is unrelated to revoke but green; I read it, did not mutate it.

CONCLUSION
PASS WITH CONDITIONS. Each behaviour the PR claims has a red test under a mutant. Three costs of the design are real and undocumented in the README: global serialisation, a second event on a retried lost reply, and an active token after a mid-revoke crash. Conditions, none blocking:
- C1 F-C701-1: replace the global lock with a lock per token id (or document that all revokes serialise and bound the ledger timeout).
- C2 F-C701-2/-3: state in the README that a retried revoke can write a second event with a new revocation id, and that a crash between event and write leaves the token active until retried; consider reusing the revocation id on retry (derive it from the token id) so the second event is recognisable.
- C3 F-C701-4: a reconciliation or an alert for a delegation.revoke event whose token is still active.

FINDINGS
F-C701-1 MEDIUM-LOW, services/delegation-authority/src/delegation_authority/api.py (the revoke block, around the new "with app.state.revoke_lock"): one global lock across the ledger call. PROVEN.
F-C701-2 LOW-MEDIUM, same block: retried revoke after a lost ledger reply writes a second event with a new revocation id. PROVEN.
F-C701-3 LOW-MEDIUM, same block: crash between append and store write leaves an active token with a revoke event. PROVEN (simulated).
F-C701-4 LOW, services/delegation-authority/src/delegation_authority/store.py (save_revoked): cross-process race can still yield two events; documented in the code comment only. HIGH.
F-C701-5 INFO, tests/test_revoke_c625.py: no test for different tokens being revoked concurrently (objection 1 passes every test).

NOT VERIFIED: CI; a real crash or a real second process (threads only); behaviour under the real ledger client's timeout; GX10 run.
