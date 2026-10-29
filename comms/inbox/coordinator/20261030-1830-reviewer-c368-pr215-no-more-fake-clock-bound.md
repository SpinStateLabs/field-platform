# C-368 reviewer report (Lane 5): PR 215 test/no-more-fake-clock-bound-c357 @7d62c57 (C-357; my C-350 F-C350-1)

VERDICT: PASS on the exact head 7d62c57 (one file, 13 insertions, clean on current main 241a941). The fake clock now raises after 1000 clock calls, so the no-sleep mutant that hung the old test fails in 0.34 s with a clear assertion; no assertion or test changed (106 collected before and after); the bound is 38 times above the largest legitimate use; all 14 earlier mutants still die. Class and file:line only; no values.

OBJECTIONS FIRST
1. Nothing blocks. One reading note: in a whole-file run (my mutation runner) the no-sleep mutant took 101 s to die, because the estate-backed tests earlier in the file run first (about 100 s) and the fake-clock tests come last; the failure itself takes 0.34 s when the `_no_more` tests run alone. The "fails in seconds" claim holds for the test, not for the file. LOW. [HIGH, run]
2. One commit on main 250bda8 (current main 241a941; the file is unchanged on main between them as far as the merge shows: clean); author and committer Don Hagell noreply. [HIGH]

ASSUMPTIONS
1. Own worktrees on the GX10 for the head and for 250bda8; the mutants run on the head. [HIGH]

REASONING
1. Card item (1), the bound: `_Clock` (tools/tests/test_phase_g_check.py, the class the five `_no_more` tests use) gains `MAX_CALLS = 1000`, a call counter, and `_tick()`, which raises `AssertionError("the wait made more than 1000 clock calls without finishing")` once exceeded; `time()` and `sleep()` both tick. The no-sleep mutant (deleting `time.sleep(0.25)` in `_no_more`, tools/phase_g_check.py:275) on the head, only the five `_no_more` tests: two fail (`test_no_more_waits_the_whole_window_when_nothing_arrives` and `test_no_more_window_is_the_settle_window_capped_at_three_seconds`) with that assertion, real 0.34 s. The same mutant on the base (PR 201's file): still running when `timeout 20` killed it, i.e. it hangs. [HIGH, run]
2. Card item (2), nothing else touched: `git diff 250bda8 7d62c57` is the class docstring, `MAX_CALLS`, the counter, `_tick()` and the two `self._tick()` calls; no assertion line or test body changed; collected tests in `tools/tests/test_phase_g_check.py`: 106 on the base and 106 on the head. [HIGH, run and read]
3. Card item (3), the bound is not too low: replaying the five scenarios with the head's clock: an event after a few polls uses 7 clock calls; nothing arriving with a 1.5 s window 14; the cap test (window forced to 30 s, capped at 3.0 s inside `_no_more`) 26; already above 1; unreadable ledger 1. The most any window `_no_more` can wait is `min(SETTLE_S, 3.0)` = 3.0 s at 0.25 s steps, about 26 calls; the bound is 1000, a factor of 38. The five tests, unmutated, passed 25 times in 25 runs (`-k no_more`). [HIGH, run]
4. Card item (4), mutants (15 on tools/phase_g_check.py, the whole file as judge, bytecode caching off, 900 s limit): killed 15 of 15: the nine exit-status and NOT-VERIFIED mutants from C-278 and C-335 (91 to 93 s each, 4 s for the dropped check), the five `_no_more` mutants (no wait, window zero, cap 3.0 raised to 30, `<=` turned `<`, never refetching: 29 to 103 s) and the no-sleep mutant (101 s in the whole-file run, 0.34 s alone). [HIGH, run]
5. Public-repo hygiene: tests only. [HIGH]

CONCLUSION
PASS on 7d62c57; C-350 F-C350-1 closed. No new cards.

What I did NOT do: run the full verify or CI (the coordinator's); run the other tools modules after this change (the file is self-contained for this class).
