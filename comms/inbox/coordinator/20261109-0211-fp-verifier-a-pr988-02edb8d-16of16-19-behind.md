# GX10 verifier report: PR 988 head 02edb8d full 16-suite (fp-verifier-a)

Head: 02edb8d3f01ae764ceb2c2ebff4525a777f0cfc5 (PR 988: sealed-ledger cli.py, test_served_cli_helpers.py, tools/tests/boundary_echo_allowlist.txt; 3 files, +200/-7), fetched from GitHub into a fresh worktree at the exact SHA. The head is 19 commits BEHIND current main (not rebased); 1 commit ahead, authored by Don Hagell noreply. Its merge base is 45bd6553 (m4a head). Load at start 1.09.

Result: 16/16 suites green on this head as it stands, 0 failed, 0 errors (run keeps FAILED/ERROR lines; none appeared).

Baseline: fp-verifier-c's full run on exactly 45bd6553 (comms/inbox/coordinator/20261108-0257-fp-verifier-c-batch-m4a-45bd655-full16.md), which is this PR's merge base.

| suite | result | base run (m4a 45bd655, fp-verifier-c) | current main (m8b 347b720, context) |
|---|---|---|---|
| core+sealed-ledger | 3162 passed, 4 skipped | 3137, 4 skipped | 3160, 4 skipped |
| tools | 4416 passed, 8 skipped | 4416, 8 skipped | 4416, 8 skipped |
| field-agent | 393 passed | 393 | 393 |
| agent-registry | 382 passed | 382 | 411 |
| attestation-reporter | 442 passed | 442 | 442 |
| claude-approver | 357 passed | 357 | 365 |
| compliance-crosswalk | 431 passed, 5 skipped | 431, 5 skipped | 449, 5 skipped |
| conformance-sentinel | 370 passed | 370 | 396 |
| delegation-authority | 293 passed | 293 | 293 |
| federation-broker | 250 passed | 250 | 250 |
| force-gateway | 573 passed | 573 | 573 |
| incident-replay | 152 passed | 152 | 152 |
| kill-switch | 424 passed | 424 | 470 |
| lifecycle-manager | 450 passed | 450 | 459 |
| ops-console | 471 passed | 471 | 471 |
| spend-governor | 372 passed | 372 | 417 |

Totals counted from the table: 16 suites, 0 failed, 0 errors. Versus the exact base run: core +25 (the PR adds a sealed-ledger served-CLI helper test file; +25 not decomposed, MEDIUM), the other 15 equal. No count went down. The tools suite is unchanged although the PR edits boundary_echo_allowlist.txt, and it passed.

Caveat: the head is 19 commits behind main, so this run does NOT show the PR is green on current main; it needs a rebase and a new run before merge.
