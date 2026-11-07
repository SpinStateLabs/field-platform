# ssl-ff-builder-9: B-RB-PR387-98de2c7 -> NEW draft PR 865 (rebuild of PR 387)

PR: https://github.com/SpinStateLabs/field-platform/pull/865 (draft). Head 07ade47b38f32535e3e7a2c986ed690a22750b4a on main 41afda502; 10 commits (9 cherry-picks plus 1 test pin), author AND committer Don Hagell noreply, trailers Sonnet 5.5 only; remote head verified. PR 387 itself untouched.
BLOCK fixed: F-R387-1 (no merge base) by rebuild: 9 commits cherry-picked without conflict; `767925973` dropped (already on main, empty). Diff vs main equals the reviewer's measured 10 files +1295 -48 before my pin; nothing under .github/.
F-R387-2 (R7): pinned (3 cases), mutant killed. F-R387-3 (R10): already pinned by test_a_tmpfs_volume_device_is_not_a_path in test_compose_pr345_conditions_c715.py; with R10 applied it fails, so nothing added (the reviewer ran a 7-file set that did not execute that parametrisation).
Tests: 7 files referencing the tools: 1054 passed, 8 skipped, 2 failed; the 2 failures fail identically on a main-based tree (Windows symlink and docker), baseline. CI not read.
For the coordinator: the PR is wider than its title (C-715, C-823, C-932, C-1049); the reviewer suggested splitting C-932/C-1049; the C-932 and --realpath behaviours still have no mutants. Please close PR 387 once 865 is accepted.
