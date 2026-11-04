# Lane O reviewer: PR 500 (S-A3, ledger refuses NaN/Infinity in an event payload; plus a docs anchor commit) @34ebca6d03975a7d49433a2e83fcedd3fae4c2ea. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 34ebca6d. Lane A (field-core, sealed-ledger). Two commits on main cd3b7690 (contains main: yes), all Don Hagell noreply as author and committer (HIGH). I did not write the head. Claimed through dispatch.sh (R-PR500-000fbee, an abbreviated head 000fbee that no longer matches the live head 34ebca6d: the PR moved after the list was written; this report is on 34ebca6d, the head at review time).

Objections first: (1) the check lives in make_event and in the API validator, so events already in a ledger with a NaN keep reading as tampered; the PR does not repair or flag them (out of scope, but /verify on an affected estate stays red). (2) the walker only descends dict values and list/tuple items: sets, Decimal and float dict KEYS are not descended. Probe (run, HIGH): float-key {nan:1} is refused by pydantic (ValidationError), set and Decimal('NaN') are refused by JSON serialisation (TypeError); none is accepted, so no hole found, but the guarantee rests on three different layers, not on this function. (3) tuple payloads can only come from the Python API, never JSON, so the tuple branch is untested (survivor below).

The docs commit (ENVIRONMENT.md anchor FIELD_EXPORT_ROOT sealed_ledger/api.py:464 to :471): run `python tools/environment_anchors.py --check` on the head: 0 wrong anchor row(s) (HIGH). The +7 shift equals the 7 lines of the new validator.

Run here (cloud, relative PYTHONPATH): packages/field-core new file 23 passed, whole suite 1567 passed, 2 skipped; sealed-ledger new file 4 passed, whole suite 806 passed, 5 skipped, 1 error: tests/test_operator_observer_c6_serve.py spawns a `ledger serve` subprocess and fails identically on current main in this environment (baseline, not this PR). NOT run: the 16-suite set, CI.

Mutants (28 run, scratch worktree on the exact head; core mutants run against the core file then the sealed-ledger file, survivors against the whole suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 refuses NaN/inf/-inf anywhere (isnan only, isinf only, drop dict, drop list, drop tuple, top level only, call removed, depth one) | 8 | 7 | 1 |
| B2 finite numbers and lookalike strings accepted (refuse any float, big, -0.0, "nan" strings) | 4 | 4 | 0 |
| B3 message carries no value or key (value, repr, text, type) | 4 | 4 | 0 |
| B4 deep payload no recursion error (recursive, depth cap, early stop, truncate lists) | 4 | 3 | 1 |
| B5 API: 422 and nothing appended (noop, validator removed, wrong field, keys only) | 4 | 4 | 0 |
| B6 finite payload still appends and verifies (rejects all, returns empty, returns None, rounds floats) | 4 | 3 (2 by older tests) | 1 |
| Total (counted from the rows) | 28 | 25 | 3 |

Survivors (3, all LOW real pin gaps):
- F-O500-1: the tuple branch (list only) is unpinned; no test passes a tuple payload (ledger.py reject_non_finite).
- F-O500-2: a walker that stops after a few siblings (return when the stack holds more than 3 items) survives; no test has a wide payload with the non-finite value LAST.
- F-O500-3: the API validator that rounds floats in the stored payload survives; the finite test checks only status 201 and /verify, never that the stored payload equals the posted one.

CONDITIONS (blocking): C1 CI green and a GX10 16-suite run on the exact head rebased on current main (code PR; I could not run it). C2 none other.
Optional, NEW PR only after the head is frozen: F-O500-1/2/3 pins; a note or card for pre-existing NaN events (objection 1).

Tokens/cost line: not available to me. I do not know.
