# GX10 verifier ssl-ff-verifier-5: V-RUN-BATCH-m10-250154d

Verdict: **16/16 suites PASS** (0 failed, 0 errors) on head **250154d3f87181585227f279821efb6c5dcbc84e** (batch/2026-11-06-m10; m9 head f7408db5 is an ancestor; checked-out HEAD == full SHA verified; load avg 0.72). HIGH.

| suite | result |
|---|---|
| core+sealed-ledger | 2695 passed, 4 skipped |
| tools | 4072 passed, 4 skipped |
| field-agent | 229 passed |
| agent-registry | 314 passed |
| attestation-reporter | 300 passed |
| claude-approver | 322 passed |
| compliance-crosswalk | 392 passed, 5 skipped |
| conformance-sentinel | 284 passed |
| delegation-authority | 257 passed |
| federation-broker | 191 passed |
| force-gateway | 452 passed |
| incident-replay | 123 passed |
| kill-switch | 270 passed |
| lifecycle-manager | 287 passed |
| ops-console | 471 passed |
| spend-governor | 337 passed |

16 rows, 16 pass. Versus the m9 head f7408db5 run: no suite count went down (core 2695 vs 2617, tools 4072 vs 4033, rest equal) (HIGH).
Log: ~/ff-work/ver5m10-all.log on the GX10.
