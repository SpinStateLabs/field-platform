VERDICT PASS on a58525753143c9235b5bbe1ffc1385cb7189a2e3 (PR 325, Q-20, Lane 15 reviewer; delta from 2ab0e8a, last verdict C-961 PASS WITH CONDITIONS; UNVERIFIED: cloud, no GX10, no CI logs)

OBJECTIONS (first)
1. A fixed window (2026-11-01 to 2027-03-31) is not a deadline: after 2027-03-31 nothing goes red, so a stale helper can still outlive its date (C-961 condition 2 stays open; the coordinator chose no check against today's date, builder note 20261101-0246-builder-lane1-c1012.md).
2. Moving the date needs two edits (docstring and window); a reviewer who edits only one gets a red test, which is the intent, but an editor who widens the window silently defeats it.
3. Delta rule: I judge only the new commit on top of 2ab0e8a; the earlier verdict covers the rest. Verified below that the delta is test-only.
ASSUMPTIONS: head current (git ls-remote = full sha); the delta 2ab0e8a..a585257 is one file, tools none: packages/field-core/tests/test_operator_auth.py (+8 -3, git diff --stat) (HIGH).

REASONING
1. Baseline: field-core 1123 passed, 1 skipped (matches the builder's figure); the two operator-auth files 176 passed (HIGH, run).
2. Date mutants on the removal-date line (both helper docstrings changed together): 2099-01-31, 2020-01-31, 2026-10-31, 2027-13-45, 2027-04-01 and 2027-1-31 each FAIL the test (6 of 6 killed); the boundaries 2026-11-01 and 2027-03-31 PASS, as the window says (HIGH). So the window is inclusive at both ends and the parse is strict ISO.
3. Wording mutants: dropping "Removal date:" fails the test (killed); removing "(proposed, not yet a ruling)" survives, so the docstring's "proposed" status is not pinned (LOW, by design: the test cannot judge a ruling).
4. All mutated files restored; worktree status clean. merge-tree vs main clean.
5. F-C325-1 (the date test accepted any past or far date): CLOSED by the window (HIGH).

FINDINGS
- F-Q20-1 LOW: the "proposed" wording is unpinned (above).
- F-Q20-2 LOW: after 2027-03-31 the window gives no signal; C-961 condition 2 (a ruling, or a test that goes red on the date) stays with the coordinator. Not a regression.

NOT VERIFIED: CI on this head; callers outside this repository (same limit as C-961).

CONCLUSION: PASS. The delta closes F-C325-1; conditions 1 and 2 from C-961 (open the removal card, rule on the date) remain non-blocking and unchanged.
