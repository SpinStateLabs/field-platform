# Review PR 552 @ 86082cccaf0c5d2074b0693dfb7b9661033fb8e6 (claude-approver: an overflowing usage-cursor value disables posting) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head 86082ccc. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head still required.

## Objections first
1. The failure it fixes is a double-posting of usage to the governor (money). A fix that catches the new exception but leaves the cursor "loaded with empty data and no error" would hide the same fault; the test asserts the error string, no posts across two ticks, and zero tick errors.
2. Only `OverflowError` is added. Other corrupt shapes are caught by the existing handler, but they are not pinned by this PR (survivors below, all pre-existing).
3. `int()` accepts floats (truncated), numeric strings and bools, so a cursor with `1.5` or `"5"` loads silently as an integer. Not part of this PR; I did not test what a negative value does downstream (not run).

## Facts (HIGH)
- Head fetched via refs/pull/552/head = 86082ccc; 2 commits (a fix and a merge of main `b963407a`); contains current main; author AND committer on both: Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 2 files, +18 -1: `claude_approver/core.py` (one exception added to the tuple in `UsageCursor.load`), `tests/test_approver_usage.py` (+17, one test).
- Baseline unmutated: claude-approver suite 316 passed (relative `PYTHONPATH`).
- Red first, measured by mutant O1 below: with `OverflowError` removed the new test fails (1 failed, 315 passed).

## Mutants (the whole claude-approver suite each time; file restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| the claimed fix: OverflowError caught, error set, message exact, no empty-data load (O1, O4, O5, O6) | 4 | 4 | 0 |
| other exception classes in the same handler (O2 ValueError, O3 TypeError) | 2 | 1 | 1 (O3) |
| cursor file shape and read errors (S1 non-dict top level, S2 non-dict snapshot, S4 OSError, S5 missing file) | 4 | 1 (S5) | 3 (S1, S2, S4) |
| load runs once (S3) | 1 | 0 | 1 (S3) |
| no-op control (O7: my edit changed nothing) | 1 | 0 | 1 (EQUIVALENT, my construction) |
Totals counted from the table: 4+2+4+1+1 = 12 rows; killed 4+1+1+0+0 = 6; survived 0+1+3+1+1 = 6; anchor failures 0.

## Survivors (none in the PR's claim; all pre-existing gaps)
- F-R552-1 LOW-MEDIUM (O3, S1, S2, S4): a cursor with `null` values (TypeError), a list at the top level, a non-dict snapshot, or an unreadable file is not pinned by any test; the handler is correct on the paths I reasoned about, but a refactor could drop one silently. For S1 without the ValueError the code would raise an `AttributeError`, which the handler does not catch (a crash, not a double post). Pin each corrupt shape once, as this PR does for overflow.
- S3 is near-equivalent (reloading each time gives the same result); O7 is a no-op of mine.

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head.
