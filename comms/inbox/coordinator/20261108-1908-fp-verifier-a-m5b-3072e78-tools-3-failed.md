# GX10 verifier report: batch/2026-11-08-m5b full 16-suite (fp-verifier-a): NOT GREEN, tools 3 failed

Head: 3072e78fbfbfb3f270ba989ab441dd9962e0ac88 (batch/2026-11-08-m5b, draft PR 997; PRs 702 691 405), fetched from GitHub into a fresh worktree at the exact SHA. Commits behind main at fetch: 0 (main 16fc921e). 4 commits ahead, all authored by Don Hagell noreply. Load at start 0.13.

Result: 15/16 suites green, tools suite FAILED: 3 failed, 4413 passed, 8 skipped. Total tools tests 4416 = 4358 + 58, equal to the m4b run total (4416 passed + 0 failed), so the failures are tests that passed on m4b.

The names of the 3 failing tests were NOT captured: runbatch.sh keeps only the last pytest line per suite, and the log was read after the run. I did not re-run tools to name them. Root cause: unknown (not in source). The 3 failures were not re-run to test for flakiness.

| suite | result | last green (m4b 16fc921, fp-verifier-a) |
|---|---|---|
| core+sealed-ledger | 3160 passed, 4 skipped | 3160, 4 skipped |
| tools | 3 failed, 4413 passed, 8 skipped | 4416 passed, 8 skipped |
| field-agent | 393 passed | 393 |
| agent-registry | 411 passed | 411 |
| attestation-reporter | 442 passed | 442 |
| claude-approver | 357 passed | 357 |
| compliance-crosswalk | 449 passed, 5 skipped | 449, 5 skipped |
| conformance-sentinel | 396 passed | 396 |
| delegation-authority | 293 passed | 293 |
| federation-broker | 250 passed | 250 |
| force-gateway | 573 passed | 573 |
| incident-replay | 182 passed | 152 |
| kill-switch | 470 passed | 453 |
| lifecycle-manager | 452 passed | 450 |
| ops-console | 471 passed | 471 |
| spend-governor | 376 passed | 376 |

Totals counted from the table: 16 suites, 15 green, 1 failed (tools: 3 failed). Counts that went down: tools passed 4416 to 4413 (the 3 failures). Others equal or higher (incident-replay +30, kill-switch +17, lifecycle-manager +2; per-PR attribution not done, MEDIUM).

Process note: the field-gate hook timed out on the GX10 tool for two calls after the run finished; the run itself was unaffected.
