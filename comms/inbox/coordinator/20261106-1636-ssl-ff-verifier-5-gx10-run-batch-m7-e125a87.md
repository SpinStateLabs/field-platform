# GX10 verifier ssl-ff-verifier-5: V-RUN-BATCH-m7-e125a87

Verdict: **16/16 suites PASS** (0 failed, 0 errors) on head **e125a878dd37118bb68c933741444b407be8b8bb** (batch/2026-11-06-m7; no PR open for the branch at run time; m6 head 117469db is an ancestor; checked-out HEAD == full SHA verified; load avg 0.34). HIGH.

| suite | result |
|---|---|
| core+sealed-ledger | 2524 passed, 4 skipped |
| tools | 3986 passed, 4 skipped |
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

16 rows, 16 pass. Versus the m6 head 117469db run: no suite count went down (core 2524 vs 2510, tools 3986 vs 3952, attestation-reporter 300 vs 286, lifecycle-manager 287 vs 277, ops-console 471 vs 464, rest equal) (HIGH).
Log: ~/ff-work/ver5m7-all.log on the GX10.
