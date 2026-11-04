# Reviewer report: PR 487 @ce2876e4 (operator_auth: retired key refused at the highest generation seen, C-1147)

Reviewer: ssl-ff-reviewer-2. All runs UNVERIFIED (cloud, no GX10). Python 3.13, relative PYTHONPATH (field-core `src`). HIGH CARE: authentication path (packages/field-core/src/field_core/operator_auth.py, `_apply_retired_memory`).

## Verdict: PASS WITH CONDITIONS (head ce2876e4bb4d7042685de05b0a8ece2944191a02)
Conditions: C1 rebase on current main (PR base is cd3b7690, main is 97dcfec1, conflict not checked); C2 GX10 16/16 on the exact rebased head; C3 CI green; C4 coordinator confirms Don's ruling text for C-1147 matches the "narrow rule" as coded (I could not read the ruling: it is not in the diff; the test docstring cites "Don's ruling 2026-11-02 on PR 355 F-C847-1/-2", I did not verify it) . No blocking code finding.

## Objections first
1. New refusal path in the authentication code: a key retired at any generation below the high is now refused at the high generation, where the old test (`generation <= retired[hash]`) accepted it. Intended by the ruling; every operator whose key legitimately re-appears in a second file of the same generation now gets 403 (HIGH, reading plus test 1).
2. A file at a new high clears every key it contains from the retired table. Anyone who can write an operators file at a higher generation can resurrect a retired key. Same trust as before (file write already controls the registry), but the narrow rule widens what a higher-generation file can undo from "keys removed below its generation" to "all keys it holds" (MEDIUM, reading).
3. Memory is per process, first load refuses nothing, restart forgets. Unchanged and pinned by test_the_first_load_of_a_file_refuses_nothing (HIGH).
4. Comment block above `MAX_RETIRED_HASHES` now has a dangling parenthesis "(a restored backup, a stale ``.prev``)" after the new sentence; the text reads wrong (LOW, operator_auth.py around line 1245-1252, read from the diff).
5. The retired table is capped (MAX_RETIRED_HASHES = 4096, oldest evicted); an evicted key is accepted again. Pre-existing, not touched (HIGH).

## Scope and identity
2 files: field_core/operator_auth.py (+14/-3), tests/test_operator_retired_key_narrow_rule_c1147.py (new, 160). 1 commit; author AND committer = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). `tools/environment_anchors.py --check`: 0 wrong anchor rows (HIGH). Test keys are marked fake ("not-a-real-key"); no real credential seen (HIGH).

## Runs
Baseline (unmutated head): PR test file 8 passed; existing operator_auth suites (test_operator_auth, _format2, _stage0, _blank_env, _machine_verifier) 389 passed. A mutant is KILLED when the PR test file fails; for survivors I also ran the five existing files.

## Mutants (operator_auth.py)
| Id | Behaviour | Mutation | PR tests | Existing suites |
|---|---|---|---|---|
| N1 | narrow refuse | pre-PR condition `generation <= retired[h]` restored | KILLED | n/a |
| N2 | narrow refuse | refuse only strictly below the high | KILLED | n/a |
| N3 | narrow refuse | refuse only if retired below the high | KILLED | n/a |
| N4 | narrow refuse | table never refuses | KILLED | n/a |
| R1 | re-issue clears | clear on new high removed | KILLED | n/a |
| R2 | re-issue clears | only one present key cleared | SURVIVED | KILLED (test_operator_auth_format2.py::test_retired_against_the_highest_generation_seen) |
| R3 | re-issue clears | whole table cleared on new high | KILLED | n/a |
| R4 | re-issue clears | cleared keys stamped 0, still in table | KILLED | n/a |
| R5 | re-issue clears | clears the wrong keys | KILLED | n/a |
| H1 | new high | `>=` for `>` (same generation is a new high) | KILLED | n/a |
| H2 | new high | every load is a new high | KILLED | n/a |
| H3 | new high | only the first load is a new high | KILLED | n/a |
| H4 | new high | a gap of 1 is required | KILLED | n/a |
| L1 | lower file (unchanged code, control) | below-high "lacks keys" refusal removed | SURVIVED | KILLED (existing suites, 2 failed) |
| L2 | lower file (unchanged code, control) | `<=` for `<` | SURVIVED | SURVIVED |

Counted from the table: 15 rows. In scope for the PR (N, R, H) = 13: PR tests KILLED 12, SURVIVED 1 (R2, killed by an existing suite, so 13 of 13 killed by the combined tests). Per behaviour: narrow refuse 4/4, re-issue clears 4/5 by PR tests (5/5 combined), new high 4/4. Controls L1, L2 are unchanged code, outside the PR's claim: L1 killed by existing suites, L2 survived everything (I do not know whether L2 is equivalent; not examined, not this PR).

## Findings
- F1 LOW (HIGH confidence, run): R2. PR tests never give a new-high file two or more retired keys, so clearing only one passes; only an older test catches it. Add a case with two retired keys re-issued in one file (new PR).
- F2 LOW: objection 4, the comment text; fix wording in a new PR.
- F3 MEDIUM, owner call: objection 2; the coordinator may want Don to confirm that "a higher-generation file resurrects any key it holds" is intended.

## Not verified
Rebase on 97dcfec1; CI; GX10; the text of Don's C-1147 ruling; behaviour with a format 1 file or next_key rows under the new clear (test files use single-key rows; `_row_slot_hashes` includes next_key hashes, so `present` covers them by reading, not by run).
