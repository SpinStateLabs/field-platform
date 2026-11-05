# GX10 verifier ssl-ff-verifier-5: V-RUN-BATCH-m4-25775af

Verdict: **16/16 suites PASS** (0 failed, 0 errors) on head **25775af858969417c55c16f85aa9aff32fce57ac** (batch/2026-11-05-m4, draft PR 814, base main; 869cf2ed is an ancestor; checked-out HEAD == full SHA verified; load avg 1.42). HIGH.

| suite | result |
|---|---|
| core+sealed-ledger | 2463 passed, 4 skipped |
| tools | 3864 passed, 4 skipped |
| field-agent | 229 passed |
| agent-registry | 314 passed |
| attestation-reporter | 286 passed |
| claude-approver | 321 passed |
| compliance-crosswalk | 392 passed, 5 skipped |
| conformance-sentinel | 279 passed |
| delegation-authority | 257 passed |
| federation-broker | 191 passed |
| force-gateway | 452 passed |
| incident-replay | 123 passed |
| kill-switch | 270 passed |
| lifecycle-manager | 277 passed |
| ops-console | 464 passed |
| spend-governor | 331 passed |

16 rows, 16 pass. Versus the m3 head 3804d0b9 run earlier today (also on 869cf2ed): no suite count went down; core 2463 vs 2458, tools 3864 vs 3835, field-agent 229 vs 212, attestation-reporter 286 vs 277, compliance-crosswalk 392 vs 375, others equal or higher (HIGH).
Log: ~/ff-work/ver5m4-all.log on the GX10.
