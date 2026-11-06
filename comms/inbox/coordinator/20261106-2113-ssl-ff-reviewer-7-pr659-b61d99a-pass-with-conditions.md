# Review PR 659 (S4-11: lifecycle-manager api: unique persist temp name; /findings fixed 500 for non-object state; blank operator 422) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `b61d99a8f86886b1bbd69c3c3f84c974c1900fce`.
Conditions: C1 (test portability, with a Windows-only behaviour finding): on the unmodified head, `test_many_threads_writing_one_path_never_raise_and_leave_valid_json` FAILS deterministically here (3 of 3 runs): 302+ `PermissionError(13, 'Access is denied')` from `os.replace`. On Windows, replacing a file that another thread is replacing or has open raises, so the unique temp name does not remove the race on that platform; on Linux (where the estate runs) `os.replace` is atomic and I expect the test to pass, but I did not run Linux. Mark the stress test Linux-only or retry on PermissionError, and show it green on the GX10/CI. C2: the head is based on b963407a, main has moved (250154d3) and a trial merge conflicts in docs/ENVIRONMENT.md only (anchor rows): rebase with `tools/environment_anchors.py --fix`. C3: CI and GX10 on the landed head. The PR text warns that #605 and #498 edit other hunks of the same file.

## Checks (HIGH, run by me)
- Identity: 3 commits, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on all 3; trailers Sonnet 5.5; .github/: 0 files. 3 files: lifecycle_manager/api.py (+32/-7), tests/test_persist_and_findings_shapes.py (+226), docs/ENVIRONMENT.md (+2/-2).
- Code read: `_persist` writes to a temp name unique per write (`<name>.<pid>.<thread>.<random>.tmp`) with the ordinary umask mode (not `mkstemp`, which would make the file 0600), `os.replace`s it, and removes the temp on any failure including a BaseException; `_load` raises unless the JSON is an object; `/findings` answers a fixed `500 lifecycle state unreadable` (no path, no OS text) for an OSError or ValueError on either state file; `SweepRequest.operator` is stripped, a blank one is a 422, and the maximum is 200.
- Tests on the exact head (Windows): test_persist_and_findings_shapes.py 36 passed, 1 failed (C1), 1 deselected counts: with the stress test deselected 36 passed. The PR reports lifecycle-manager 302 passed (Linux-style run, not reproduced).

## Mutants (20; run with the Windows-failing stress test deselected, so the baseline is green; counted from the table)
| group | mutants | killed | survived |
|---|---|---|---|
| temp name and cleanup T1-T9 (shared name, no pid, no thread id, no random, no cleanup, cleanup only for Exception, cleanup swallows the error, 0600 mode, written in place) | 9 | 5 | 4 (T2, T3, T6, T8) |
| /findings L1-L5 (non-object accepted, list only, leaks the error, OSError / ValueError not caught) | 5 | 5 | 0 |
| operator O1-O6 (not stripped, blank allowed, max removed / 201 / 100, default changed) | 6 | 6 | 0 |
Totals: 20 mutants, 16 killed, 4 survived (9+5+6 = 20; 5+5+6 = 16; 4+0+0 = 4).
Correction for the record: my first pass of these 20 reported 20 of 20 killed, but that run included the failing stress test, which made every mutant "fail" trivially; I discarded it and re-ran on a green baseline.
Survivors: T2 and T3 (the pid and the thread id parts of the temp name) are likely killed by the stress test on Linux, which I could not run here; T6 (a KeyboardInterrupt or other BaseException does not remove the temp file) is unpinned; T8 (0600 mode) is unpinned here because POSIX mode bits do not exist on Windows, so the PR's mode test cannot discriminate (it can on Linux).

## Not verified
CI/GX10; Linux (where T2, T3, T8 and the stress test should be re-checked); the PR's 302-test count.
