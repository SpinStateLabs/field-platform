# GX10 verifier ssl-ff-verifier-5: V-RUN-PR387-98de2c7

Verdict: **16/16 suites PASS** (0 failed, 0 errors) on head **98de2c778176d0d4da7dbbd347ed240895a67923** (PR 387, draft, base the stacked branch test/compose-resolved-realroots-c823; very old base, counts far below current main; checked-out HEAD == full SHA verified). HIGH.

| suite | result |
|---|---|
| core+sealed-ledger | 1865 passed, 4 skipped |
| tools | 3543 passed, 4 skipped |
| field-agent | 151 passed |
| agent-registry | 304 passed |
| attestation-reporter | 135 passed |
| claude-approver | 282 passed |
| compliance-crosswalk | 353 passed, 5 skipped |
| conformance-sentinel | 256 passed |
| delegation-authority | 213 passed |
| federation-broker | 105 passed |
| force-gateway | 443 passed |
| incident-replay | 91 passed |
| kill-switch | 160 passed |
| lifecycle-manager | 224 passed |
| ops-console | 246 passed |
| spend-governor | 242 passed |

16 rows, 16 pass. 'No count went down' is NOT asserted: head is on an older main than the newest green GX10 log, so counts below that log (e.g. core 2350 vs 2398) are most likely base drift (MEDIUM). Landing needs 16/16 on the head rebased on current main.
Log: ~/ff-work/ver5p387-all.log on the GX10.
