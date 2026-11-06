# builder-6: B-RT-pr818-test-order (F-818-1)
PR 818 head 35f06096 carries reviewer-7 PASS WITH CONDITIONS, so I did not push to it: stacked PR 827 https://github.com/SpinStateLabs/field-platform/pull/827 (base = PR 818's branch claude/determined-noether-pbg5bo-g22-secret), head a6d524daff78574a545643584959f2d5f00aa28d. Author+committer Don Hagell noreply. One test file, +3 lines (autouse fixture resets oh._reset_internal_state() before and after each test).
Reproduced first: c801 then test_operator_health -> 1 failed, 87 passed. Now 88 passed; reset removed -> fails again. Whole field-core suite 1647 passed, 2 skipped.
Coordinator: merge 827 after 818 (retarget to main), or fold it into 818's head if you accept an unreviewed push there. Review requested.
