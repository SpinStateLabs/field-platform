# GX10 verifier report: PR 978 head c5b8daa full 16-suite (fp-verifier-a)

Head: c5b8daa16efc5d0b0cc826dbeb3d56629f3b59c2 (PR 978: spend-governor README.md and test_readme_cited_tests_exist.py; 2 files, +68/-1), fetched from GitHub into a fresh worktree at the exact SHA. The head is 40 commits BEHIND current main (not rebased); 1 commit ahead, authored by Don Hagell noreply. Load at start 0.97.

Result: 16/16 suites green on this head as it stands, 0 failed, 0 errors (run keeps FAILED/ERROR lines; none appeared).

Baseline: the clean old base, taken as the count my earlier old-base PR runs (949 to 976) agree on per suite (MEDIUM: inferred from agreement, not a run of the bare base).

| suite | result | clean old base | current main (m8b 347b720, context) |
|---|---|---|---|
| core+sealed-ledger | 2946 passed, 4 skipped | 2946, 4 skipped | 3160, 4 skipped |
| tools | 4358 passed, 8 skipped | 4358, 8 skipped | 4416, 8 skipped |
| field-agent | 295 passed | 295 | 393 |
| agent-registry | 382 passed | 382 | 411 |
| attestation-reporter | 442 passed | 442 | 442 |
| claude-approver | 357 passed | 357 | 365 |
| compliance-crosswalk | 431 passed, 5 skipped | 431, 5 skipped | 449, 5 skipped |
| conformance-sentinel | 370 passed | 370 | 396 |
| delegation-authority | 293 passed | 293 | 293 |
| federation-broker | 250 passed | 250 | 250 |
| force-gateway | 573 passed | 573 | 573 |
| incident-replay | 132 passed | 132 | 152 |
| kill-switch | 424 passed | 424 | 470 |
| lifecycle-manager | 450 passed | 450 | 459 |
| ops-console | 471 passed | 471 | 471 |
| spend-governor | 385 passed | 372 | 417 |

Totals counted from the table: 16 suites, 0 failed, 0 errors. Versus the clean old base: spend-governor +13 (the PR adds a test that README-cited tests exist; +13 not decomposed, MEDIUM), the other 15 equal. No count went down.

Caveat: the head is 40 commits behind main, so this run does NOT show the PR is green on current main; it needs a rebase and a new run before merge.
