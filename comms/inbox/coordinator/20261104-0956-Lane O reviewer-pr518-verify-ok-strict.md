# Lane O reviewer: PR 518 (scout S-C5, attestation-reporter and incident-replay: INTACT only for ok is True) @e6b0b657b849a435e516aa9e4e20ce70e087b3d5. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head e6b0b657. Lane B (attestation-reporter, incident-replay). One commit on main cd3b7690 (contains main: yes), Don Hagell noreply as author and committer (HIGH); two small source changes (attestation-reporter engine.py +7/-1, incident-replay engine.py +8/-2) and two test files (+79, +47). I did not write the head. Claimed through dispatch.sh (R-PR518-e6b0b65).

Objections first: (1) strictness changes behaviour for a ledger that answers `"ok": 1` or `"ok": "true"`: both services now say "not verified", where `1` and `"true"` used to read INTACT (a deliberate fail-closed narrowing; if the sealed-ledger ever serialises ok as a non-boolean this PR turns every integrity line unverified at once) (read, HIGH; I did not check the ledger's own /verify model). (2) the two services word the same condition differently: attestation-reporter reports a metric "unavailable" and incident-replay a post-mortem "unverified"; both fail closed (read, HIGH), but a reader comparing them sees two vocabularies. (3) the busy-ledger rule is unchanged: a "ledger busy:" reason is only recognised when ok is falsy.

Run here (cloud, scratch worktree on e6b0b657, relative PYTHONPATH of every service src and packages src): attestation-reporter new file 20 passed, whole suite 275 passed; incident-replay new file 18 passed, whole suite 115 passed. NOT run: the 16-suite set, CI.

Mutants (26 run in a scratch worktree; each against the PR's own test file of that service, survivors against the whole service suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| A1 attestation-reporter: a non-boolean ok is unavailable, never INTACT or BROKEN | 5 | 5 | 0 |
| A2 attestation-reporter: INTACT only for ok is True | 4 | 3 | 1 |
| A3 attestation-reporter: a false ok is BROKEN with the reason; ledger busy unchanged | 4 | 3 | 1 |
| I1 incident-replay: a non-boolean ok is unverified, never intact or broken | 5 | 4 | 1 |
| I2 incident-replay: intact only for ok is True | 4 | 3 | 1 |
| I3 incident-replay: a false ok is unverified when busy, else broken with the reason | 4 | 4 (2 by older tests) | 0 |
| Total (counted from the rows) | 26 | 22 | 4 |

Survivors (4): 1 equivalent, 3 weak pins.
- Equivalent (read, HIGH): `"INTACT" if v["ok"]` instead of `is True` in attestation-reporter: the new guard above already ensures a bool, so the two expressions agree.
- F-O-pr518-1 LOW: the busy-ledger test in attestation-reporter does not combine `ok: true` with a "ledger busy:" reason; dropping `not v.get("ok") and` survives (a contradictory answer; unpinned, near-equivalent).
- F-O-pr518-2 LOW: the incident-replay unverified note loses its "— retry the replay" ending unnoticed (the test checks the status, not the full text).
- F-O-pr518-3 LOW: the "chain intact over N events" detail can be shortened to "chain intact" unnoticed; the event count in the detail is unpinned.

CONDITIONS (blocking): C1 CI green and a GX10 16-suite run on the exact head rebased on current main (code PR; I could not run it). C2 a one-line check, recorded, that the sealed-ledger `/verify` answer is a JSON boolean today (objection 1): that PR is strict on the receiving side only.
Optional, NEW PR only after the head is frozen: F-O-pr518-1..3 pins.

Tokens/cost line: not available to me. I do not know.
