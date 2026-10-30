# C-444 reviewer report (Lane 5): PR 286 @78ef879 (C-440; my C-439 F-C439-1), tests only

VERDICT: PASS on the exact head 78ef879 (one commit directly on main 3287f03, current main; author and committer Don Hagell noreply). Three cases added to the helper's "flags" list in `tools/tests/test_operator_keygen.py` (+3): exactly the first 9 characters of the made-up key, exactly the last 9, and a 9-character run at an odd offset. Both boundary mutants I named at C-439 (the scan one window short at the end, and one late at the start) now go red; so do five further scan-range and window-size mutants. Whole tools suite on the head: 2735 passed, 4 skipped, 0 failed (python -m pytest -q tools/tests, 487 s). No finding. No key value was printed or kept: the helper tests use a made-up key string and the suite uses temp-directory test keys.

OBJECTIONS FIRST
1. None that change the verdict. The helper remains a substring-window oracle: it does not catch a re-encoded key (reversed, chunked), and it allows runs of 8 or fewer characters by design; both limits were recorded at C-439 and the PR does not claim otherwise. LOW, no action. [HIGH]
2. The extra odd-offset case (`KEY[1:1 + KEY_WINDOW]`) is the PR's own addition beyond my two boundary cases; it kills a scan that skips every other offset, which I had not named. [HIGH, run]

ASSUMPTIONS
1. Own GX10 worktrees at the head (one for the full suite, a second for the mutants so the running suite was not edited under it); the suite with PYTHONPATH from the worktree's package, service and defence-shield `src` directories; mutants by my runner on the helper (test_operator_keygen.py lines 20-60; the file as judge; bytecode caching off). [HIGH]

REASONING
1. Diff: three entries appended to the `leak` parametrisation of `test_the_helper_flags_a_message_with_key_material`: `KEY[:KEY_WINDOW]`, `KEY[-KEY_WINDOW:]`, `KEY[1:1 + KEY_WINDOW]`, each with a comment saying which scan error it catches. Nothing else changed. [HIGH, read]
2. Helper mutants (12 hand): killed 12. The scan one early (last window never compared) and one late (first window never compared), both my C-439 survivors; every other offset; every third offset; two early; two late; the slice one character short or one long; only offset 0 and the tail checked; a case-insensitive match; the helper never flagging; the helper always flagging. [HIGH, run]
3. Whole tools suite: 2735 passed, 4 skipped (2660 passed, 4 skipped at C-439's head; main has gained tests since, and this PR adds 3 of the difference). [HIGH, run]
4. C-439 F-C439-1 is closed. [HIGH]

CONCLUSION
PASS on 78ef879. No card proposed.

What I did NOT do: run CI (the coordinator's); re-run the production-side refusal-text mutants of C-439 (unchanged by this PR); Windows.
