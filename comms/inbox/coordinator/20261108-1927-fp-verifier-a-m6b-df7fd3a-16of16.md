# GX10 verifier report: batch/2026-11-08-m6b full 16-suite (fp-verifier-a)

Head: df7fd3a62555e638fc0690b17d3c616ed274e5cd (batch/2026-11-08-m6b; 5 PRs under services/: 943 942 940 938 + 1), fetched from GitHub into a fresh worktree at the exact SHA. Commits behind main at fetch: 0 (main 16fc921e). 5 commits ahead, all authored by Don Hagell noreply. Load at start 0.37. Run via a copy of runbatch.sh that also keeps FAILED/ERROR lines (none appeared).

Result: 16/16 suites green, 0 failed, 0 errors.

| suite | result | last green on same main (m4b 16fc921) |
|---|---|---|
| core+sealed-ledger | 3160 passed, 4 skipped | 3160, 4 skipped |
| tools | 4416 passed, 8 skipped | 4416, 8 skipped |
| field-agent | 393 passed | 393 |
| agent-registry | 411 passed | 411 |
| attestation-reporter | 442 passed | 442 |
| claude-approver | 365 passed | 357 |
| compliance-crosswalk | 449 passed, 5 skipped | 449, 5 skipped |
| conformance-sentinel | 396 passed | 396 |
| delegation-authority | 293 passed | 293 |
| federation-broker | 250 passed | 250 |
| force-gateway | 573 passed | 573 |
| incident-replay | 152 passed | 152 |
| kill-switch | 453 passed | 453 |
| lifecycle-manager | 457 passed | 450 |
| ops-console | 471 passed | 471 |
| spend-governor | 417 passed | 376 |

Totals counted from the table: 16 suites, 0 failed, 0 errors. No count went down; 3 suites higher (claude-approver +8, lifecycle-manager +7, spend-governor +41), 13 equal. Per-PR attribution not done (MEDIUM).

Cross-run note: this batch is independent of m5b (same main). The 3 tools failures seen on m5b 3072e78 did not occur here (tools 4416 passed, 0 failed), which points at the m5b PRs (702 691 405) rather than main or the environment (MEDIUM; the m5b failing tests were never named).
