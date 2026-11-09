# GX10 verifier report: PR 984 head 6bae7d7 full 16-suite (fp-verifier-a)

Head: 6bae7d7f50f2350b44a59808e9b5a41be7edbdc7 (PR 984: lifecycle-manager engine.py plus test_decommission_text_bounds.py; 2 files, +86/-0), fetched from GitHub into a fresh worktree at the exact SHA. The head is 41 commits BEHIND current main (not rebased); 1 commit ahead, authored by Don Hagell noreply. Its merge base is 2bc5643e (pre-m3 main). Load at start 1.66.

Result: 16/16 suites green on this head as it stands, 0 failed, 0 errors (run keeps FAILED/ERROR lines; none appeared).

Baseline: the clean old base on the 2bc5643e line, taken as the count my earlier PR runs on that line (949 to 978) agree on per suite (MEDIUM: inferred from agreement, not a run of the bare base 2bc5643e).

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
| lifecycle-manager | 459 passed | 450 | 459 |
| ops-console | 471 passed | 471 | 471 |
| spend-governor | 372 passed | 372 | 417 |

Totals counted from the table: 16 suites, 0 failed, 0 errors. Versus the clean old base: lifecycle-manager +9 (the PR adds a decommission text-bounds test; +9 not decomposed, MEDIUM), the other 15 equal. No count went down.

Caveat: the head is 41 commits behind main, so this run does NOT show the PR is green on current main; it needs a rebase and a new run before merge.
