# Review PR 500 (scout S-A3, HIGH CARE sealed-ledger: refuse NaN/Infinity in an event payload) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `bc533b77e7fe182d1069af009a63a097e96570b5`.
Conditions: C1 (landing): the head is based on cd3b7690, main has moved (250154d3) and a trial merge conflicts in docs/ENVIRONMENT.md only (anchor rows): rebase with `tools/environment_anchors.py --fix`, then re-run the anchors check. C2: CI and GX10 on the landed head (a ledger append path). No defect found in the code.

## Checks (HIGH, run by me)
- Identity: 3 commits, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on all 3; trailers Sonnet 5.5; .github/: 0 files. 5 files: field_core/ledger.py (+22), sealed_ledger/api.py (+9/-2), two new test files (+45, +35), docs/ENVIRONMENT.md (+1/-1).
- Defect and fix confirmed by my own probe through the real sealed-ledger app (`POST /events` with raw JSON bodies): `NaN`, `Infinity`, `-Infinity`, `1e999`, `-1e999` (Python's json parses `1e999` as infinity, which a NaN-only check would miss), a NaN inside a nested list in a dict, and a 3,000-deep nested payload all answer 422 with the fixed `Value error` body (no value, no key echoed) and append nothing. A finite payload with the strings "nan" and "Infinity", a 30-digit integer and `-0.0` answer 201, and `GET /verify` stays ok with 3 events stored. The PR's own account is right: before this change one such request made the chain read as tampered, because the seal hashed a NaN token while the served JSON carried null.
- Code read: `reject_non_finite` is iterative (a deep payload cannot hit the recursion limit), walks dict values and lists and tuples, and raises a fixed message; `make_event` calls it, so every in-process sealer is covered, and `AppendRequest.payload` calls it through a field validator so the HTTP route answers 422 before the store is touched. `_canonical_bytes` and the hashing of existing events are unchanged, so an already-written ledger verifies as before (the PR notes a stored event that already holds NaN keeps verifying as before).
- The "other writers not audited" point from the PR: I grepped the other sealing sites. `make_event` is called by the store at its two internal sites (store.py:2007 and :2131), so they inherit the guard; the two direct `LedgerEvent(**record, ...)` constructions (store.py:485, ledger.py:161) build events from already-validated records or `make_event`'s own partial. I did not read the CLI or `/export` payload paths beyond that.
- Tests on the exact head (Windows): field-core test_ledger_non_finite_sa3.py 23 passed; sealed-ledger test_append_non_finite_sa3.py 4 passed. The PR also reports field-core 1567 and sealed-ledger 806 passed (one environment error in a `ledger serve` subprocess test, baseline); I did not re-run those whole suites.

## Mutants (11; each killed if either test file fails; counted from the table)
| # | mutant | result |
|---|---|---|
| G1 | `make_event` guard removed | KILLED (field-core) |
| G2 | API validator removed | KILLED (sealed-ledger) |
| F1 | `isfinite` replaced by a NaN-only check | KILLED |
| F2 | only infinity refused | KILLED |
| F3 | float check removed | KILLED |
| W1 | dict values not walked | KILLED |
| W2 | lists not walked | KILLED |
| W3 | tuples not walked | SURVIVED |
| W4 | no descent below the top level | KILLED |
| M1 | the message echoes the value | KILLED |
| M2 | the walk drops all but one sibling (a stack truncation bug) | SURVIVED |
Totals: 11 mutants, 9 killed, 2 survived (9+2 = 11). W3 is LOW: JSON cannot produce a tuple, so the HTTP route is unaffected; an in-process caller could. M2 shows the tests have no case with a non-finite value in the MIDDLE of three or more siblings (`{"a":1,"b":NaN,"c":2}`), so a walk bug that skips siblings would pass; add that shape.

## Not verified
CI/GX10; Linux; the whole field-core and sealed-ledger suites on this head; the CLI and `/export` payload paths; any real ledger already holding a NaN event.
