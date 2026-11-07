# Review PR #865 (compose resolved-model hardening, rebuild of PR 387 on main) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `07ade47b38f32535e3e7a2c986ed690a22750b4a`. No conditions. Three optional notes.

## Facts (HIGH, read from the head)
- 10 commits on merge base `41afda502`. All authored and committed by `Don Hagell <13129187+dhagell@users.noreply.github.com>`. Nothing under `.github/`.
- Rebuild integrity: the 9 cherry-picked commits have the same patch-id as PR 387's 9 commits (compared pair by pair); I found no drift. The 10th (`07ade47b3`) is new and adds only `tools/tests/test_compose_pr345_conditions_c715.py` (R7: a named volume with `driver_opts` and no device). No tool code changed in it.
- Files: `tools/compose_bind_rules.py`, `tools/compose_resolved_check.py`, one runbook line, 7 test files. No other source files.

## Verification (run by me, Windows 10, Python 3.14)
- The 7 test files: 1054 passed, 8 skipped, 2 failed. The 2 failures (`test_a_symlinked_source_is_followed_only_with_realpath`, `test_docker_runs_only_with_run_compose_and_only_for_config`, both in `test_compose_resolved_bind_c512.py`) fail the same way on main `ff06b3398`: docker is not on PATH here and symlinks need privilege. Baseline, not PR defects.
- Hand mutants (mine, 10, one at a time, the 7 files run with those 2 tests deselected; files restored, tree clean afterwards). Counted from the output: 7 RED, 3 survived.
  - RED: PyYAML-missing exit changed 3 to 1; PyYAML-missing message removed; `realpath(__file__)` replaced by `abspath`; sibling `except Exception` narrowed to `ImportError`; sibling-failure exit 3 to 1; sibling-failure message changed; `network_mode` refusal branch disabled (`bridge` allowed).
  - Survived: (a) `sys.path.insert(0, ...)` changed to `append`; (b) the allowed roots not resolved under `--realpath`; (c) the source not resolved under `--realpath`.

## Reading the survivors
- (b) and (c): the tests that pin them (`test_compose_pr353_conditions_c823.py`, the symlink test in `_c512`) need real symlinks and are among the 8 skipped or the deselected one on this host. I could not run them. MEDIUM: they go red on Linux; the builder reports 16 of 16 on GX10 on the old head `98de2c778` (not re-run on this head, which differs only by the new test file). I did not verify this.
- (a): LOW. `append` only changes behaviour if another `compose_bind_rules` earlier on the path shadows the sibling; a test would need to plant one. Optional.

## Prior conditions
C-43 (copied-alone exit, `bridge` wording) and the C-1049 delta (PyYAML-missing, stale or broken sibling: exit 3, one line) are met and each is pinned: the matching mutants above are red.

## Optional (LOW)
1. Add a test planting a shadow `compose_bind_rules.py` earlier on the path, to pin `insert(0, ...)`.
2. The tool is still not wired into a deploy gate (C-43's third point); out of this PR's scope.
3. Re-run the symlink and `--realpath` tests on Linux or GX10 on this head.

## Not covered
CI and GX10 on this head; Linux (symlink tests); a real `docker compose config`.
