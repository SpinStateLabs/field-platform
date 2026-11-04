# Reviewer report: PR 360 @ c5fddb5459512135f9168ee899747a97858f046a (C-128, spend-governor burst boundary and window_start docs)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Base 5808a5cd (old); 4 commits; 2 files (+199): spend_governor/core.py (a docstring only, +12, no code change) and tests/test_burst_boundary_c128.py (+187). Author and committer of all 4 = Don Hagell 13129187+dhagell@users.noreply.github.com; trailers Sonnet 5.5 (HIGH). `git merge-tree --write-tree origin/main pr360` clean (HIGH).

## Objections first
1. The docstring added to `window_start` makes a behavioural claim about six routes ("answers 500 and records nothing" for a stored row with an unknown period); the only test on it asserts that the words appear in the docstring (test_window_start_docstring_states_the_utc_precondition), not that the routes behave so.
2. A stored-row fallthrough that "fails toward counting more" is described, not tested; a regression that makes `window_start` count LESS would only be caught by other suites.
3. Tests use a frozen clock and exact microsecond offsets; they pin the inclusive burst edge but a 60 s window against a wall clock with sub-microsecond skew is not exercised (not claimable by this PR).

## Verified
- Baseline on the exact head: tests/test_burst_boundary_c128.py 17 passed; whole services/spend-governor/tests 259 passed (relative PYTHONPATH).
- I checked the docstring's claim by running it (not in the PR): with a cap row stored with period 'weekly' through direct SQL, GET /caps, GET /status, GET /totals, GET /usage, POST /spend and POST /usage each answered 500, and the spend and usage tables stayed at 0 rows (HIGH). So the six-route statement is true on this head; it is simply not pinned.

## Mutants (scratch worktree on the head; baseline 17 passed in the PR's file; kill = at least one failure there)
| # | Mutant | Result | Killed |
|---|---|---|---|
| B1 | burst `>=` -> `>` | 5 failed | yes |
| B2 | burst threshold limit+1 | 5 failed | yes |
| B3 | burst detail drops the limit | 1 failed | yes |
| B4 | burst detail drops the count | 1 failed | yes |
| B5 | no limit treated as 0 | 1 failed | yes |
| W1 | window_tokens `ts>=` -> `ts>` | 2 failed | yes |
| W2 | window_tokens sums input tokens only | 4 failed | yes |
| W3 | token_rows_after `ts>` -> `ts>=` | 1 failed | yes |
| U1 | API clock keeps the caller's offset | 2 failed | yes |
| U2 | naive clock no longer assumed UTC | 17 passed | NO |
| S1 | window_start monthly -> daily | 17 passed | NO (killed by other suite tests: 5 failed) |
| S2 | window_start fallthrough -> today | 17 passed | NO (killed by other suite tests: 5 failed) |
| S3 | window_start daily -> hourly | 17 passed | NO (killed by other suite tests: 3 failed) |
| S4 | docstring drops "answers 500 and" | 1 failed | yes |
Totals counted from the table: 14 valid mutants, 10 killed by the PR's file, 4 survived it (U2, S1, S2, S3). Run against the whole services/spend-governor suite (baseline 259 passed): S1 5 failed, S2 5 failed, S3 3 failed, so those three are killed elsewhere; U2 survives the whole suite, also when run under TZ=America/Toronto (259 passed), so it is a true survivor. Excluded: my S5 (docstring still contains "UTC" elsewhere, an ineffective mutant). The burst boundary, the window edges and the UTC conversion, which are what the PR claims to pin, are killed 9 of 9 (B1-B5, W1-W3, U1).

## Findings
- F-C128-1 LOW: objection 1; add a test that stores a cap row with an unknown period and asserts the six routes answer 500 and record nothing (I ran this and it holds).
- F-C128-2 LOW: U2, the naive-datetime clock branch (api.py `_now`, `tzinfo is None` -> UTC) is unpinned.
- F-C128-3 LOW: the window_start behaviours are pinned only outside this PR's files (S1-S3 killed elsewhere); fine, noted.

## Verdict: PASS on c5fddb5459512135f9168ee899747a97858f046a
Head frozen; LOWs go in a NEW PR. Merge is clean against current main (base 5808a5cd is old): CI green and GX10 16/16 on this exact head rebased on current main per the coordinator procedure. Not run by me: CI, GX10.
