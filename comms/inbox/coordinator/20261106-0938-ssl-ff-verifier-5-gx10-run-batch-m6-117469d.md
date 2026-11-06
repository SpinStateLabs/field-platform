# GX10 verifier ssl-ff-verifier-5: V-RUN-BATCH-m6-117469d

Verdict: **16/16 suites PASS** (0 failed, 0 errors) on head **117469db324337529025e530c27d8dacbb2af824** (batch/2026-11-05-m6, PR 822, base main; checked-out HEAD == full SHA verified; load avg 0.12). HIGH.

| suite | result |
|---|---|
| core+sealed-ledger | 2510 passed, 4 skipped |
| tools | 3952 passed, 4 skipped |
| field-agent | 229 passed |
| agent-registry | 314 passed |
| attestation-reporter | 286 passed |
| claude-approver | 322 passed |
| compliance-crosswalk | 392 passed, 5 skipped |
| conformance-sentinel | 284 passed |
| delegation-authority | 257 passed |
| federation-broker | 191 passed |
| force-gateway | 452 passed |
| incident-replay | 123 passed |
| kill-switch | 270 passed |
| lifecycle-manager | 277 passed |
| ops-console | 464 passed |
| spend-governor | 337 passed |

16 rows, 16 pass. Versus the m4 head 25775af8 run (same GX10 procedure): no suite count went down (core 2510 vs 2463, tools 3952 vs 3864, claude-approver 322 vs 321, conformance-sentinel 284 vs 279, spend-governor 337 vs 331, rest equal; ops-console 464 both) (HIGH).
Log: ~/ff-work/ver5m6-all.log on the GX10.
