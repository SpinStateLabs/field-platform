# Review PR 827 (reset the internal-route denied counter around tests; red team F-818-1; stacked on #818) — ssl-ff-reviewer-7

**VERDICT: PASS** on head `a6d524daff78574a545643584959f2d5f00aa28d` (tests only, 3 lines; no conditions beyond landing order).
Landing order: base is PR 818's branch (head 35f06096, which carries my PASS WITH CONDITIONS and is not pushed to). 827 cannot land before 818, then retarget to main.

## Checks (HIGH, run by me)
- Identity: 1 commit above 818's head, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>; trailer Sonnet 5.5 only. .github/: 0 files. Diff vs 818: 1 file, packages/field-core/tests/test_operator_internal_secret_c801.py, +3: `oh._reset_internal_state()` before the autouse fixture's yield, and again after it. The fixture is `autouse=True`, so every test in the file is covered. No source change.
- Tests on the exact head (Windows): c801 + test_operator_health 88 passed; the reverse order 88 passed; whole field-core suite 1647 passed, 2 skipped (the PR says the same).
- The hole is real and is closed: removing both resets makes the suite fail again (1 failed, 143 passed, the health-fields test, as the red team reported: counter 35 != 0).

## Mutants (3; counted from the table)
| # | change | result |
|---|---|---|
| R1 | post-test reset removed | KILLED (1 failed) |
| R2 | pre-test reset removed | SURVIVED (equivalent in the orderings run: the previous test's post-reset already leaves the counter at 0) |
| R3 | both resets removed | KILLED (1 failed) |
Totals: 3 mutants, 2 killed, 1 survived (2+1 = 3). R2 is an equivalent-in-practice survivor (defence against a previous file that left the counter dirty).

## Notes (LOW, optional)
- Two test files reset the counter (this one and test_internal_secret_stage2_gate_g22.py). Other files that can trigger denials (for example test_operator_rotation_r2.py's ENFORCE verify-hash test) do not reset it; the default order and the two orders I ran pass, but the state is process-global, so a future file that triggers a denial without resetting would reintroduce the same order-dependence. A single autouse fixture in conftest.py would remove the class of bug.

## Not verified
CI/GX10; Linux; random test orderings beyond the two I ran.
