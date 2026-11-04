# Reviewer (lane B, incident-replay): PR 499 (scout P-15) refuse a replay window with since later than until

**Verdict: PASS WITH CONDITIONS on head `357abe74415706cd3fa9892ba0be4a8088d4879a`.** Head unchanged at start and end (git ls-remote); base main cd3b7690; 1 commit, Don Hagell noreply on author and committer. Not built by this lane.

Diff (HIGH, read): engine.py +10/-1 adds `ReplayRequest._window_is_ordered`, a `model_validator(mode="after")` that raises when `_instant(since) > _instant(until)`; the message names neither bound. `_instant` treats a naive stamp as UTC (engine.py:73-81), so naive and aware bounds never raise a TypeError. Both `/replay` and `/replay/markdown` take `ReplayRequest`, so one validator covers both (api.py:45, 49). New test file `test_replay_window_order.py`, 5 tests.

## Objections first
1. A naive bound next to an aware one: handled by `_instant` (naive = UTC); not tested (LOW).
2. Leap seconds or `24:00` forms: `datetime.fromisoformat` rejects them at the existing per-bound validator, so they never reach the new one (MEDIUM, reasoning not run).
3. A caller that relied on an inverted window returning an empty report now gets 422: intended, a behaviour change, not a regression.
4. The error text could echo a bound through the FastAPI 422 `input` field; the test asserts the response text holds "2030-01" nowhere (it passes, via the repo's no-echo 422 handler).

## Measured (GX10 ~/ff-work/wt-ln499, load under 1, relative PYTHONPATH, own venv with typer)
New file 5 passed. incident-replay suite: PR 102 passed vs main cd3b7690 97 passed (+5, no count down). CI when read: 2 SUCCESS, 5 with no conclusion (pending), so NOT 7/7. 16-suite not run by me.

## Mutants (25 rows; source restored after each, worktree clean)
Run 1 had 21 rows (20 killed, 1 survived); the survivor changed only the type annotation of the markdown route and left it validating, so it was an invalid mutant. Run 2 replaced it with 4 real bypasses.
| Behaviour pinned | Killed | Survived |
|---|---|---|
| B1 inverted window refused (API and model) | 5 | 0 |
| B2 the markdown route refuses it too | 3 (validator-shape) + 3 (route-bypass) = 6 | 2 (my invalid mutants: annotation-only and a no-op `if False`) |
| B3 equal bounds accepted (inclusive) | 4 | 0 |
| B4 compared as instants, not strings | 4 | 0 |
| B5 message names neither value | 4 | 0 |
Totals counted from the table: killed 5+6+4+4+4 = 23, survived 0+2+0+0+0 = 2, 25 rows. Both survivors are invalid mutants, so no pinned behaviour is unguarded.

## Conditions
- C1: CI 7/7 SUCCESS on this exact head (5 of 7 had no conclusion when read).
- C2: GX10 16-suite 16/16 on a head containing main; the PR body says Cloud/UNVERIFIED.

## Findings (non-blocking; new PR only)
- F-499-1 LOW: no test with a naive bound beside an aware one (objection 1).
- F-499-2 LOW: no test that the CLI (`incident_replay.cli`, PR 485 / C-1204) surfaces the 422 text; that belongs to C-1204.
- INFO: PR 485 (CLI tests) is a sibling draft; no overlap in files.
