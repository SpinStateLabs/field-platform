# Review PR #498 (lifecycle-manager: sweep windows are 1..3650 days in the API and the CLI, scout P-11) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `c8d00fa62784c53c2acf21b85538fa42a4cb581e`. This head is the follow-up to ssl-ff-reviewer-2's PASS WITH CONDITIONS on `3cbef1b5` (comms/inbox/coordinator/20261104-1026-ssl-ff-reviewer-2-reviewer-pr498-3cbef1b.md); its C1 (rebase on current main) is met by a merge, C2 and C3 are the gates, and its F1 is an optional LOW that is still open.

## Facts (HIGH, read from the head)
- 3 commits (ca04cb68, 3cbef1b5, c8d00fa6 a merge of origin/main); 3 files against main at the time of the merge: services/lifecycle-manager/src/lifecycle_manager/api.py (+7/-2), cli.py (+5/-2), tests/test_sweep_request_bounds.py (new, 100 lines). Nothing under .github/.
- All three commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- Main has moved on since the merge (it is now `41afda50`); `git merge-tree --write-tree origin/main HEAD` writes a tree without conflicts, so the branch still merges cleanly.
- The code: `SweepRequest.expiry_days` and `reattest_days` are `Field(ge=1, le=MAX_SWEEP_DAYS)` with `MAX_SWEEP_DAYS = 3650` (ten years; `now +/- timedelta(days=N)` overflows near 10**9, which was a 500), and the CLI's `--expiry-days` and `--reattest-days` take `min=1, max=MAX_SWEEP_DAYS` with the same constant copied into cli.py; a test pins that the two constants agree.
- No other caller of these windows exists outside the lifecycle-manager and its tests (grep of the whole repo, docs and HTML included); the scheduled tick uses the defaults 30 and 90.

## Earlier reviewer's findings, on this head
- C1 (rebase): met by merging main (no conflict). The merge changed nothing in the PR's own diff.
- F1 (the CLI's lower bound, new in this PR, is unpinned): still open, and the builder left it as an optional follow-up card (B-FU-PR498-cli-lower-bound). Measured below.
- The 3650-day ceiling is a policy number for Don (objection 1 of the earlier review): a legitimate longer window now gets a 422 over HTTP or exit 2 from the CLI. Not a code defect.

## Verification (run by me, Windows 10, Python 3.14)
- tests/test_sweep_request_bounds.py: 23 passed (50 s; the CLI tests start typer).
- Mutants (mine, 14 hand mutants on api.py and cli.py, one at a time against that file; files restored with `git checkout`, tree clean afterwards). Counted from the output: 11 RED, 3 SURVIVED.
  - RED: API expiry upper bound removed; API reattest upper bound removed; API expiry `le` bound plus one; API reattest `lt` instead of `le`; API expiry lower bound `ge=0`; API reattest lower bound removed; API constant changed to 36500; CLI constant changed to 3000; CLI expiry max removed; CLI reattest max removed; CLI expiry max 10**9.
  - SURVIVED: the CLI `--expiry-days` `min=1` removed, the CLI `--reattest-days` `min=1` removed, the CLI `--expiry-days` `min` changed to 0 (all three are the open F1: the CLI now refuses 0 and negative days, which it accepted before, and no test says so).
- Not re-run on this head: the whole lifecycle-manager suite (the earlier reviewer ran 292 passed; the head differs by a main merge and an ANSI-stripping fix to the CLI test).

## Conditions
None.

## Optional LOW (new PR only; head is frozen after this PASS)
1. Pin the CLI lower bound (the three survivors above): one test that `--expiry-days 0` and `--reattest-days -1` exit 2.

## Not covered
GX10 16 of 16 and CI on this exact head; the whole lifecycle-manager suite; Linux.
