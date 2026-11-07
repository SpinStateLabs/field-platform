# Review R-PR455-89d3cfa: PR 455 (agent-incident-retro synthetic calibration corpus; C-1165), re-review after my C1
Head reviewed: 89d3cfadea16e4726c02406240cb813548100be1 (3 commits; the new one is 89d3cfad). `git merge-tree` against current main is clean (tree 64f523f9). Earlier report: head 166db1c8, PASS WITH CONDITIONS (C1: CONTEXT_BENIGN unpinned).

## VERDICT: PASS (C1 closed)

## Checks (HIGH, run by me)
1. Identity: all 3 commits author AND committer Don Hagell 13129187+dhagell noreply; nothing under `.github/`; 5 files, all under defence-shield/agent-incident-retro/tests/ (the four from before plus a 14-line addition to test_clauses.py); no source file changed.
2. Delta from the head I reviewed: one test, `test_exactly_twenty_benign_requests_before_the_first_hostile_one_are_kept`: asserts `CONTEXT_BENIGN == 20`; with 21 benign requests then a hostile one, the kept lines are 2..21 and 22 (20 benign plus the hostile); with 19 benign all are kept.
3. Tests on head: whole retro suite 270 passed, 2 skipped on two runs; one earlier run showed 1 failure (the same wall-clock test, test_signatures.py::test_cap_applies_in_every_regex_entry_point, LIMIT_S 0.2 s, seen on this host under load before; it passes on both reruns).
4. Mutants on clauses.py, re-run for the survivors of my earlier report, 3 applied (a fourth spelling did not match and was not run): 2 killed, 1 equivalent (counted from table).
| # | Mutant | Result |
|---|---|---|
| B4 | CONTEXT_BENIGN 20 -> 19 | killed (was SURVIVED) |
| B5 | CONTEXT_BENIGN 20 -> 21 | killed (was SURVIVED) |
| B7 | context slice end includes the hostile request | equivalent: the hostile request is kept by `r.is_hostile` regardless |
The 11 killed mutants of my earlier report (thresholds and boundary operators) are untouched by this commit and stand.

## Observations (LOW)
Unchanged: the corpus is synthetic and pins today's behaviour; it does not show the thresholds are right for real traffic.

## Not verified
Behaviour on real traffic; GX10 16/16.

## Head frozen at 89d3cfad.
