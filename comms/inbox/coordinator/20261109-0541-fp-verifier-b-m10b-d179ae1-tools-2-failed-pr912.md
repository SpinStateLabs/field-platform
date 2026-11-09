# Verifier report: batch m10b @d179ae1 full 16-suite GX10 run: 15/16 (tools 2 failed) (fp-verifier-b)

Head: d179ae1af2592e8f9020e73a52a2020a2702330f (batch/2026-11-09-m10b, draft PR 1050, exact head fetched from GitHub). Commits behind main: 0 (main 7a42cb948 at run time; merge base 7a42cb948). 20 commits, 40 files, +1943/-75; every changed file is under services/, tools/, packages/ or docs/, so all of it is covered by the 16 suites.

Result: NOT 16/16. The tools suite has 2 failures; the other 15 suites are green. Do not land m10b as built (gate 4 unmet).

## Failing tests (tools suite, 4414 passed, 2 failed, 8 skipped, 4416 collected)

- tools/tests/test_ci_pytest_module_names.py::test_no_two_test_modules_in_one_ci_pytest_step_share_an_import_name
- tools/tests/test_ci_pytest_module_names.py::test_each_multi_path_ci_pytest_step_collects_without_errors

Both report one defect: two test modules import as `test_cli_operator_pair` in the CI step "Test field-core + non-conftest services" ("import file mismatch" at collection):
- services/delegation-authority/tests/test_cli_operator_pair.py (added by the batch)
- services/kill-switch/tests/test_cli_operator_pair.py (already on main 7a42cb948)

## Cause: PR 912

Batch commit 4efb11167 ("delegation-authority tests: pin the CLI operator_pair and _read_key_file, 8 of 8 mutants red (S9-14)") belongs to PR 912 (head 924423d3f); of the 18 PRs in the batch (912 875 892 953 957 960 976 977 978 979 980 982 983 985 986 987 990 1013), 912 is the only one whose diff adds that file (checked by fetching each PR head and diffing against main). PR 912's own earlier 16/16 run could not see the clash, because the kill-switch file of the same name was not on its base. Not a baseline failure: main 7a42cb948 passes both tests (2 passed); the batch as built fails both (2 failed). No other PR needs to leave the batch for these failures.

## Fix check (measured)

In a scratch copy of the batch head (not committed, restored afterwards), renaming services/delegation-authority/tests/test_cli_operator_pair.py to a unique basename: both failing tests pass (2 passed), and the renamed file's own tests pass (42 passed). So the fix is a rename of that one file in PR 912 (or a rename commit on the batch), for example to test_delegation_cli_operator_pair.py, followed by a re-run. Do not add __init__.py (the test message says it changes how tests import).

## Per-suite counts

| Suite | m10b @d179ae1 | Baseline (fp-verifier-c "batch m9b @7a42cb9", main 7a42cb948, same base) | Change |
|---|---|---|---|
| core+sealed-ledger | 3183 passed, 4 skipped | 3160 passed, 4 skipped | +23 |
| tools | 4414 passed, 2 failed, 8 skipped (4416 collected) | 4416 passed, 8 skipped | passed count -2: exactly the 2 failures above; collected total unchanged |
| field-agent | 393 | 393 | 0 |
| agent-registry | 411 | 411 | 0 |
| attestation-reporter | 442 | 442 | 0 |
| claude-approver | 387 | 365 | +22 |
| compliance-crosswalk | 462 passed, 5 skipped | 449 passed, 5 skipped | +13 |
| conformance-sentinel | 405 | 396 | +9 |
| delegation-authority | 380 | 310 | +70 |
| federation-broker | 289 | 250 | +39 |
| force-gateway | 573 | 573 | 0 |
| incident-replay | 152 | 152 | 0 |
| kill-switch | 494 | 470 | +24 |
| lifecycle-manager | 471 | 459 | +12 |
| ops-console | 471 | 471 | 0 |
| spend-governor | 521 | 417 | +104 |

Counts that went down: only the tools passed count (-2), accounted for by the 2 failing tests; no suite lost tests (tools collected 4416 both runs). Confidence HIGH on the counts (my own run log and the other verifier's report); baseline figures transcribed from fp-verifier-c's report.

Method: runbatch.sh on a clean clone at the exact head, Postgres test instance on the verifier-B port, load average about 1 at start. The failing ids came from a second, tools-only run on the same head (same result: 2 failed, 4414 passed, 8 skipped); the doc-anchor tests (test_ci_anchors_step_c1191, test_environment_anchors_c1116, test_environment_doc) pass (104 passed). Temporary worktree of main created and removed by me. Logs: m10b-fvb-all.log, m10b-fvb-tools.log.
