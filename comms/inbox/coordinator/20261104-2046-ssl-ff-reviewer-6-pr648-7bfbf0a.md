# Reviewer report: PR 648 @ 7bfbf0a2 (three stacked commits: C-1147 narrow retired-key rule, C-1205 direct tests, C-1179 spend-governor CLI per-request headers)

Reviewer: ssl-ff-reviewer-6 (cloud, NO GX10; UNVERIFIED). Claim: R-PR648-7bfbf0a. Head fetched from refs/pull/648/head; on main b963407a; 5 files (+611/-15). Author and committer of all three commits: Don Hagell <13129187+dhagell@users.noreply.github.com> (HIGH). `git merge-tree` against main is clean.

## Verdict: PASS (head 7bfbf0a2) with conditions: (1) the first commit duplicates PR 487; (2) GX10 run on the head that lands (security-relevant auth code in field-core).

## Objections first (FORCE-O)
1. Three unrelated behaviours in one PR: one is an authentication rule (operator_auth retired keys), one is a CLI header change, one is test-only. A revert of one means reverting the stack. Process point, not a defect.
2. Commit 5208c74f is the SAME patch as the head commit of PR 487 (same patch-id e617180fb563 over packages/; PR 487 diff is those 2 files, +174/-3). If 487 lands first this PR must drop the commit; `git merge-tree 487 648` is clean, so it is mechanical. Whichever order, only one copy may land (HIGH, measured).
3. The narrow rule is a state machine over (last, high, retired). Tests pin eight scenarios, but a mutant that clears retired keys when a file exceeds the LAST-seen generation rather than the HIGHEST (A4) survives the PR's own file; the whole field-core suite kills it only through test_operator_auth_format2::test_retired_against_the_highest_generation_seen. The sequence 43, then 42, then 43 is the untested one (LOW; covered elsewhere).
4. `request_headers(method, path, routes)` decides by regex over the path; any new governor write route not added to GOVERNOR_TEMPLATES silently loses its operator pair. The drift test (`test_the_cli_table_equals_the_routes_the_governor_guards`) catches that against op_health.guard routes (C1, C2 kill). A guarded read would be missed only if added without the guard dependency (design; LOW).
Steelman: C-1147 closes a real hole Don ruled on (a key retired at 42 accepted again in a second file at 43); C-1179 stops the CLI sending the operator pair on reads and agent-reported /spend and /usage; C-1205 adds direct tests of two modules reached only through the store.

## Facts checked
- operator_auth.py: `new_high` computed before the high is updated; on a new high every present hash leaves the retired table; refusal is now `h in retired` (HIGH).
- cli.py: GOVERNOR_TEMPLATES lists the four guarded routes; every request goes through `_hdr(method, path)`; the rate-limit loader reads with GET (no pair) and writes with PUT (pair). Spend and usage POSTs carry the perimeter secret only (HIGH).
- No secret, host or flag added; test keys are labelled made-up (HIGH).

## Runs (UNVERIFIED, PYTHONDONTWRITEBYTECODE=1, absolute PYTHONPATH)
- new files: c1147 8 passed; c1179 12 passed; c1205 40 passed.
- whole packages/field-core/tests: 1553 passed, 1 skipped. Whole services/spend-governor/tests: 303 passed. Whole services/sealed-ledger/tests: 843 passed, 5 skipped.

## Mutants (kill = the commit's own test file; baselines 8, 12, 40 and 40 passed)
| id | mutation | result |
|---|---|---|
| A1 | re-issued keys not cleared | KILLED |
| A2 | old refusal rule `generation <= retired[h]` restored | KILLED |
| A3 | new_high uses >= | KILLED |
| A4 | new_high compared with last-seen, not highest | SURVIVED target; KILLED by whole field-core suite (test_operator_auth_format2) |
| A5 | only the first present key cleared (set order) | hash-order dependent: killed with PYTHONHASHSEED 1,3,4,5,6, passed with 2; (the first unseeded run survived) |
| A6 | new_high always true | KILLED |
| A7 | refusal needs generation strictly below high | KILLED |
| A8 | retired keys never refused | KILLED |
| C1-C11 | policies/resolve templates dropped; _hdr always or never the pair; spend, usage, loader GET carrying the pair; loader PUT, set-policy and set-cap PUT without the pair; resolve path wrong | all 11 KILLED |
| L1-L9 | filters: since/until exclusive, TypeError dropped, naive not UTC, agent and type filters dropped, bad event ts not raised, bound name omitted, as_dict swap | all 9 KILLED |
| R1-R12 | retention: days<1, >=, blank env, max/min, status order, without-manifest count, non-list registry, ledger-unreadable and registry-None status, truncation, sort, ok for no_estate | all 12 KILLED |
Total 40; 37 killed by the target files deterministically... counted as: 38 killed (A1,A2,A3,A6,A7,A8 + 11 + 9 + 12), A4 killed only by the suite, A5 seed-dependent (5 of 6 seeds). No equivalent mutants identified.
