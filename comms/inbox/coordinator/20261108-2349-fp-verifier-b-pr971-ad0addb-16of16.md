# Verifier report: PR 971 full 16-suite GX10 run (fp-verifier-b)

Head: ad0addb (exact PR head, fetched from GitHub). Commits behind main: 40 (main 347b72089 at run time; merge base 2bc5643e7). Run on the exact head, not rebased on main.
PR diff vs merge base: packages/field-core/src/field_core/alerts.py (+5/-5 lines changed), packages/field-core/tests/test_alerts_docstring_callers.py (+20) (2 files, +25/-5). Both covered by the 16 suites (field-core tests run in the first suite).

Result: 16/16 suites green, no failures, no errors.

| Suite | This run | Baseline (main-based run on merge base 2bc5643e7, pr965/pr967/pr969 logs) | Change |
|---|---|---|---|
| core+sealed-ledger | 2949 passed, 4 skipped | 2946 passed, 4 skipped | +3 (new tests in this PR) |
| tools | 4358 passed, 8 skipped | 4358 passed, 8 skipped | 0 |
| field-agent | 295 | 295 | 0 |
| agent-registry | 382 | 382 | 0 |
| attestation-reporter | 442 | 442 | 0 |
| claude-approver | 357 | 357 | 0 |
| compliance-crosswalk | 431 passed, 5 skipped | 431 passed, 5 skipped | 0 |
| conformance-sentinel | 370 | 370 | 0 |
| delegation-authority | 293 | 293 | 0 |
| federation-broker | 250 | 250 | 0 |
| force-gateway | 573 | 573 | 0 |
| incident-replay | 132 | 132 | 0 |
| kill-switch | 424 | 424 | 0 |
| lifecycle-manager | 450 | 450 | 0 |
| ops-console | 471 | 471 | 0 |
| spend-governor | 372 | 372 | 0 |

No count went down. Like-for-like: the merge base is the main on which the baseline figures were measured. Note: PR 969 (head 94af499, 25 new tests) also adds tests in packages/field-core/tests; if both land, the core+sealed-ledger count after both is not verified here.

Method: runbatch.sh on a clean clone at the exact head, Postgres test instance on the verifier-B port, load average about 1.2 at start. Log: pr971-fvb-all.log.
