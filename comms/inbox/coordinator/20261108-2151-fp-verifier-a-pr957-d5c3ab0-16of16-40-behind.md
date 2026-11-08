# GX10 verifier report: PR 957 head d5c3ab0 full 16-suite (fp-verifier-a)

Head: d5c3ab0acbf244f132ce199801e2ef80bcfc4d22 (PR 957: sealed-ledger store.py events limit plus test_events_limit.py; 2 files, +45/-1), fetched from GitHub into a fresh worktree at the exact SHA. The head is 40 commits BEHIND current main (not rebased); 1 commit ahead, authored by Don Hagell noreply. Load at start 1.47.

Result: 16/16 suites green on this head as it stands, 0 failed, 0 errors (run keeps FAILED/ERROR lines; none appeared).

| suite | result | same old-base run (PR 954 e83de30, fp-verifier-a) | current main (m8b 347b720, context) |
|---|---|---|---|
| core+sealed-ledger | 2955 passed, 4 skipped | 2946, 4 skipped | 3160, 4 skipped |
| tools | 4358 passed, 8 skipped | 4358, 8 skipped | 4416, 8 skipped |
| field-agent | 295 passed | 295 | 393 |
| agent-registry | 382 passed | 382 | 411 |
| attestation-reporter | 442 passed | 442 | 442 |
| claude-approver | 357 passed | 357 | 365 |
| compliance-crosswalk | 431 passed, 5 skipped | 431, 5 skipped | 449, 5 skipped |
| conformance-sentinel | 370 passed | 370 | 396 |
| delegation-authority | 293 passed | 293 | 293 |
| federation-broker | 250 passed | 250 | 250 |
| force-gateway | 573 passed | 656 | 573 |
| incident-replay | 132 passed | 132 | 152 |
| kill-switch | 424 passed | 424 | 470 |
| lifecycle-manager | 450 passed | 450 | 459 |
| ops-console | 471 passed | 471 | 471 |
| spend-governor | 372 passed | 372 | 417 |

Totals counted from the table: 16 suites, 0 failed, 0 errors. Versus the same-era run: core +9 (the PR adds a 40-line test file in sealed-ledger; +9 not decomposed, MEDIUM), force-gateway 573 vs 656 is lower only because the 954 run included PR 954's own 83 tests (HIGH: 954 added test_tuning_env_bounds.py; 573 equals the PR 949/952 runs and current main), other 14 equal. No regression attributable to this PR.

Caveat: the head is 40 commits behind main, so this run does NOT show the PR is green on current main; it needs a rebase and a new run before merge.
