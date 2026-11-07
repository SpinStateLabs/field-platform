# gx10-verifier-2: PR 909 full 16-suite run

Head 8a24e2f9f3843a13318e4ac1fdf57e1ab37c2c85 (equals PR head at start). Full 16-suite run on GX10 via runbatch.sh. Result: 16/16 green, 0 failures.

| suite | result |
|---|---|
| core+sealed-ledger | 2946 passed, 4 skipped |
| tools | 4275 passed, 8 skipped |
| field-agent | 295 |
| agent-registry | 382 |
| attestation-reporter | 442 |
| claude-approver | 357 |
| compliance-crosswalk | 431 passed, 5 skipped |
| conformance-sentinel | 370 |
| delegation-authority | 293 |
| federation-broker | 250 |
| force-gateway | 573 |
| incident-replay | 132 |
| kill-switch | 429 |
| lifecycle-manager | 450 |
| ops-console | 471 |
| spend-governor | 372 |

Baseline: main ccd013d (verifier-4 report 20261107-0215). Only delta: kill-switch 429 vs 424 (+5), consistent with the PR scope (kill.domain ledger payload). All other counts identical. Merge-base not computed (no origin/main ref in the GX10 repo), so base-difference not ruled out (LOW). Confidence HIGH on counts.
