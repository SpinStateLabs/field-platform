# reviewer Lane 15: Q-124, PR 477 (C-1191, ci: run environment_anchors --check as a step), head b09f6d0e21b76742ef97117d9ba9fffdd4cb469e

VERDICT: PASS on b09f6d0e21b76742ef97117d9ba9fffdd4cb469e (2 commits on main c356e205; head re-read with git ls-remote refs/pull/477/head at claim time, unmoved). A ci.yml change is workflow-security-sensitive; read as such. Local Windows run, relative PYTHONPATH (";" separated), PYTHONUTF8=1, no stdin; scratch worktree, read-only on the PR. Not a GX10 run, GitHub CI not read, merge onto main 4ef319cc not simulated (main has moved from the PR's base c356e205; the ci.yml change is +4 lines).

## OBJECTIONS FIRST (limits)
1. F-Q124-1 below: the new test does not pin four step keys; mutants on them survive.
2. I did not diagnose two failures in a related test file (see "Related tests"); I reproduced them on clean main and so cannot attribute them to the PR, but I do not know their cause.
3. Whether another open PR touches `.github/workflows/ci.yml` (the "one ci.yml PR per batch" rule): not checked here.
4. This is a workflow read plus a local run of the tests and the command; GitHub Actions itself did not run.

## WORKFLOW SECURITY (the ask)
- The change is one `run` step in the `tests` job, after the topology lint step: `python tools/environment_anchors.py --check`. Nothing else in the file moves (diff is +4 lines: the step name, two comment lines, the command). HIGH.
- Triggers unchanged: `push` on main and `pull_request`; no `pull_request_target`, no `workflow_run`. Workflow `permissions: contents: read` unchanged. No `secrets`, no new `uses:` (every existing action stays pinned by sha), no new `env`. The command is repo-local, stdlib only, read-only (`--check` never writes). It runs PR code the way every other step of this job already does, with a read-only token. HIGH.
- The step has no `continue-on-error` and no `if`, so it cannot be skipped or softened. It runs on all four matrix legs (3.11 to 3.14), four runs of a read-only tool; harmless.

## CHECKS
1. The new test file (6 tests) against main's `ci.yml` (copied out of the PR head into a scratch checkout of main, removed after): 3 failed, 3 passed, matching the PR's "3 red because the step is missing". On the PR head: 6 passed.
2. The command is real: the test builds a throwaway repo, `--check` exits 0 on a right anchor and 1 on a stale one, and 0 on this repository (`environment_anchors.py --check` on the PR head: 0 wrong anchor rows). The run uses `python -I`, so no environment path leaks in.
3. The workflow is read with the strict duplicate-key loader of `test_yaml_duplicate_keys.py` (a repeated key is refused).
4. Mutants on `.github/workflows/ci.yml` against the new test (11): 7 KILLED, 4 SURVIVED.
   Killed: the command naming another file; `--check` changed to `--fix`; `|| true` appended; `continue-on-error: true` on the step; `if: always()`; a push-only `if`; `continue-on-error: true` on the whole `tests` job.
   Survived: `shell: bash {0}` on the step; `working-directory: docs` on the step; `timeout-minutes: 1` on the step; an `env:` override on the step.
5. Related workflow tests on the PR head (6 files with ci, workflow or yaml in the name, 267 tests): 265 passed, 2 failed, both in `tools/tests/test_ci_external_ref_guard_c101.py` (`test_the_shipped_guard_matches_every_spelling_and_no_clean_page`, `test_the_old_pattern_missed_what_the_report_said`). The same two tests FAIL the same way on a clean checkout of main 4ef319cc, so they are not caused by this PR; I did not diagnose them. Lane 13 reported a different failure (`test_ci_pytest_module_names`, put down to a stale editable install in its venv): that test PASSED here, with the worktree sources on the path, which fits Lane 13's explanation.

## FINDINGS
- F-Q124-1 LOW (`tools/tests/test_ci_anchors_step_c1191.py`, `problems()`): the pin forbids `continue-on-error` and `if` but not other keys of the step. The four survivors (`shell`, `working-directory`, `timeout-minutes`, `env`) make the step fail or run differently, which fails red rather than passing silently, so this is a pin gap, not an exposure. Pin (one line): require the step's key set to be a subset of `{"name", "run"}`; that kills the four survivors and `continue-on-error`/`if` together.

## CONCLUSION
PASS on b09f6d0e: the step is the narrowest change that makes a wrong anchor a named red step, it adds no secret, permission, trigger or unpinned action, the new tests are red on main and green here, and seven of eleven mutants die (the four that survive can only make the step fail, not pass). What a PASS does not prove: GitHub CI or GX10 on this head, a clean merge onto main 4ef319cc, or whether another PR is queued ahead of it for ci.yml. After this PASS builders do not push to the branch (head-freeze); the pin in F-Q124-1 can go in a follow-up PR.
