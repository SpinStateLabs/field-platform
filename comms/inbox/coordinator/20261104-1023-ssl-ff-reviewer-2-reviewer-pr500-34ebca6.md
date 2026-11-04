# Reviewer report: PR 500 @34ebca6d (ledger refuses NaN/Infinity payloads, scout S-A3)

Reviewer: ssl-ff-reviewer-2. All runs UNVERIFIED (cloud, no GX10). Python 3.13, relative PYTHONPATH with ':' separator. HIGH CARE area (sealed-ledger, field-core ledger).

## Verdict: PASS WITH CONDITIONS (head 34ebca6d03975a7d49433a2e83fcedd3fae4c2ea)
Conditions: C1 add one assertion that the API-appended event keeps its payload (mutant P5 survives, F1); C2 rebase on current main (PR base is cd3b7690, main is 97dcfec1, conflict not checked); C3 GX10 16/16 on the exact rebased head; C4 CI green. After a PASS the head is frozen: only C1 may be pushed; F2 to F4 go in a new PR.

## Objections first
1. A fix at seal time does not repair events already sealed with NaN; they still read as tampered. Not addressed or mentioned (MEDIUM, reading only, no run).
2. Two other seal paths build a LedgerEvent from a record without reject_non_finite: field_core/ledger.py:161 and sealed_ledger/store.py:485 (both `LedgerEvent(**record, hash=compute_event_hash(record))`). I did not trace whether a caller payload can reach them; they look like re-seal of an already sealed record (MEDIUM-LOW, I do not know).
3. The scan walks dict, list, tuple only. A set, a Decimal NaN or a numpy float is not scanned (LOW, not reachable from JSON).
4. The 422 echo: test asserts the field name and token are absent from the body (services/sealed-ledger/tests/test_append_non_finite_sa3.py). Holds at this head (HIGH, baseline run).

## Scope and identity
5 files: field_core/ledger.py (+22), sealed_ledger/api.py (+9/-2), two new test files (45 + 33), docs/ENVIRONMENT.md (2 lines). 2 commits, author AND committer on both = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py --check`: 0 wrong anchor rows (HIGH).

## Runs
Baseline (unmutated head): field-core test_ledger_non_finite_sa3.py 23 passed; sealed-ledger test_append_non_finite_sa3.py 4 passed. A kill = either file fails. Full sealed-ledger suite in my env: 30 failed, 186 passed, 1 skipped, 13 errors, identical with and without mutant P5, so the existing suite does not catch P5 either (MEDIUM: the failures and errors are environmental, missing deps in my cloud env, so some tests could not run).

## Mutants
| Id | Behaviour | Mutation | Result |
|---|---|---|---|
| R1 | detect | check disabled | KILLED |
| R2 | detect | NaN only | KILLED |
| R3 | detect | inf only | KILLED |
| R4 | detect | -inf missed | KILLED |
| R5 | nesting | dict not descended | KILLED |
| R6 | nesting | tuple not descended | SURVIVED (real, LOW, F2) |
| R7 | nesting | dict keys scanned, not values | KILLED |
| R8 | nesting | only first list item | KILLED |
| R9 | nesting | list inside list skipped | SURVIVED (real, LOW, F2) |
| R10 | nesting | scan stops after 50 nodes | SURVIVED (real, LOW, F3) |
| R11 | nesting | recursive implementation | KILLED (recursion limit, 18 s) |
| R12 | message | value in message | KILLED |
| R13 | message | TypeError, not ValueError | KILLED |
| R14 | message | message text changed | KILLED |
| M1 | make_event | call removed | KILLED |
| M2 | make_event | checks empty dict | KILLED |
| M3 | make_event | only multi-key payloads | KILLED |
| P1 | api | validator body disabled | KILLED |
| P2 | api | validator on wrong field | KILLED |
| P3 | api | keys only scanned | KILLED |
| P4 | api | only payloads under 2 keys | SURVIVED (real, LOW, F3) |
| P5 | api | validator returns {} | SURVIVED (real, MEDIUM, F1) |

Counted from the table: 22 rows (detect 4, nesting 7, message 3, make_event 3, api 5). KILLED 17, SURVIVED 5, none equivalent. Kill rate 17 of 22 = 77%. Per behaviour: detect 4/4, nesting 4/7, message 3/3, make_event 3/3, api 3/5.

## Findings
- F1 MEDIUM (HIGH confidence, run): P5. test_a_finite_payload_still_appends_and_verifies checks 201 and /verify length only. A validator that returns {} would silently drop every caller payload and the test stays green. Fix (condition C1): assert `client.get("/events").json()[0]["payload"] == {"v": 1.5}`.
- F2 LOW (HIGH): R6, R9. No test has a NaN inside a tuple or inside a list directly in a list. Add `lambda v: {"a": ([v],)}` style shapes (new PR).
- F3 LOW (HIGH): R10, P4. No test puts the NaN late in a wide payload, so an early-exit scan survives. Add a payload of 1000 finite keys then one NaN (new PR).
- F4 LOW: objection 2, trace store.py:485 and ledger.py:161 callers; I do not know whether a caller payload reaches them.

## Not verified
Rebase on 97dcfec1; CI; GX10; reachability in F4.
