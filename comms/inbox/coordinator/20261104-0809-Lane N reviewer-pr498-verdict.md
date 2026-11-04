# Reviewer (lane B, lifecycle-manager): PR 498 (scout P-11) sweep windows bounded to 1..3650 days in API and CLI

**Verdict: PASS WITH CONDITIONS on head `ca04cb687db0627046e6dc8dfab8c8cefda79048`.** Head unchanged at start and end (git ls-remote); base main cd3b7690; 1 commit, Don Hagell noreply on author and committer. Not built by this lane.

Diff (HIGH, read): api.py `MAX_SWEEP_DAYS = 3650`, `le=` on `SweepRequest.expiry_days` and `reattest_days`; cli.py a second `MAX_SWEEP_DAYS = 3650` and `min=1, max=` on `--expiry-days` / `--reattest-days`; new `test_sweep_request_bounds.py` (23 tests). The overflow site is `now + timedelta(days=...)` (engine.py:597, :619, HIGH).

## Objections first
1. 3650 is the author's choice, flagged "Don decides" in the PR body: a ruling, not a defect.
2. The CLI previously accepted 0 and negatives; `min=1` is a behaviour change for CLI users (intended, matches the API's ge=1), and NO test pins it (survivors B7 below).
3. Two copies of the constant can drift; a test pins equality, so a one-sided edit fails.
4. engine.py:762 `now + timedelta(days=ttl_days)` takes another number (token TTL), outside this PR (MEDIUM, not read for bounds; I do not know if it is bounded elsewhere).

## Measured (GX10 ~/ff-work/wt-ln498, relative PYTHONPATH incl. sibling service src, own venv with typer)
New file 23 passed. lifecycle-manager suite, `--continue-on-collection-errors`: PR 284 passed, 2 failed, 1 error; main cd3b7690 261 passed, the SAME 2 failed and 1 error (missing `conformance_sentinel` module in my venv, a baseline of this environment). Passed +23, no count down. CI when read: 2 SUCCESS, 5 with no conclusion (pending). 16-suite not run by me.

## Mutants (30; `python -B`, __pycache__ cleared; source restored, worktree clean)
Method note: my first pass without `-B` showed one false survivor (mutant 14: the edit 3650 to 3651 keeps the file size and, inside one second, the stale .pyc was reused). Re-run with `-B` killed it. All counts below are the `-B` run.
| Behaviour pinned | Killed | Survived |
|---|---|---|
| B1 API upper bound (both fields) | 5 | 0 |
| B2 values 1, 30 and 3650 accepted | 4 | 0 |
| B3 zero stays 422 over the API | 4 | 0 |
| B4 API and CLI share one bound | 3 | 1 (CLI imports the constant from api: equivalent, same value) |
| B5 CLI refuses above the bound (exit 2, names the option) | 5 | 0 |
| B6 CLI accepts values inside the bound | 4 | 0 |
| B7 CLI refuses 0 (`min=1`), not claimed in the PR tests | 0 | 4 (**real gap**) |
Totals counted from the table: killed 5+4+4+3+5+4+0 = 25; survived 0+0+0+1+0+0+4 = 5; 30 mutants. 1 survivor equivalent, 4 are one real gap.

## Conditions
- C1: CI 7/7 SUCCESS on this exact head (5 of 7 had no conclusion when read).
- C2: GX10 16-suite 16/16 on a head containing main; the PR body says Cloud/UNVERIFIED.

## Findings (non-blocking; new PR only)
- F-498-1 LOW-MEDIUM: nothing tests `--expiry-days 0` / `--reattest-days 0` against the CLI (4 survivors): the `min=1` the PR adds could be dropped unnoticed. One parametrised test.
- F-498-2 LOW: engine.py:762 `timedelta(days=ttl_days)` not looked at for the same overflow class (objection 4).
- INFO: the CLI 2-exit assertion accepts either `--expiry-days` or `expiry_days` in the output, so a rename of the option text would not be caught.
