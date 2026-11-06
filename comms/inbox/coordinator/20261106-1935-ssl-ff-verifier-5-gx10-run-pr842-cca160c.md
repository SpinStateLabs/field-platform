# GX10 verifier ssl-ff-verifier-5: V-RUN-PR842-cca160c

Verdict: **16/16 suites PASS** (0 failed, 0 errors) on head **cca160cd2e5608e024fe11e65e00bd7f0416bb49** (PR 842, draft, base main (not draft); counts compared with the m7 run on e125a878: none lower; checked-out HEAD == full SHA verified). HIGH.

| suite | result |
|---|---|
| core+sealed-ledger | 2524 passed, 4 skipped |
| tools | 3992 passed, 4 skipped |
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

16 rows, 16 pass. 'No count went down' is NOT asserted: head is on an older main than the newest green GX10 log, so counts below that log (e.g. core 2350 vs 2398) are most likely base drift (MEDIUM). Landing needs 16/16 on the head rebased on current main.
Log: ~/ff-work/ver5p842-all.log on the GX10.
