gx10 verifier B: C-1137 three-times-identical check of the whole tools suite on main 05942b98. Result: IDENTICAL on all three runs, 0 tests differ. (measured on the GX10; read, not guessed)

- Head: main 05942b984e5338f56ebfd5597a57f0b9c22307a3 (PR 431), read from GitHub before and after (unchanged). Worktree on the GX10 at that sha, tools/tests only, CI=true, no random ordering plugin, cache off.
- Run 1: 3749 passed, 4 skipped, 1 warning, 516.89 s (started 07:36:00Z GX10 clock).
- Run 2: 3749 passed, 4 skipped, 1 warning, 517.91 s (07:44:38Z).
- Run 3: 3749 passed, 4 skipped, 1 warning, 517.03 s (07:53:16Z).
- Per-test comparison from the junit file of each run (outcome by classname::name): 3753 testcases in each run, passed 3749 and skipped 4 in each, 0 failures, 0 errors. Tests that differ between runs: 0 (none to list). Same 4 skips each time.
- Scope and limit: this covers the tools suite only (the card's scope), on one machine and one load level (load average about 1 throughout), in file order. It does not cover other suites, parallel load or a different test order, so it cannot show order-dependent or load-dependent flakes. HIGH confidence in the three-run result; LOW confidence that no flake exists elsewhere.
- Side note for C-1135 (speed): each tools run takes about 8.6 minutes, which is most of the 16-suite wall time (core 1.9 min, ops-console 2.1 min, the rest under 1 min each).
- Files (GX10): ~/ff-work/c1137-all.log, c1137-run1.xml, c1137-run2.xml, c1137-run3.xml, c1137-diff.py (worktree wt-c1137b).
