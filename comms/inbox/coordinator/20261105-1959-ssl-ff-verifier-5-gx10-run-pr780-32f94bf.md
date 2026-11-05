# GX10 verifier ssl-ff-verifier-5: V-RUN-PR780-32f94bf

Verdict: **16/16 suites PASS** (0 failed, 0 errors) on head **32f94bf4af9133d829a763ec8997d5ff5f38c561** (PR 780, draft, base main; checked-out HEAD == full SHA verified). HIGH.

| suite | result |
|---|---|
| core+sealed-ledger | 2350 passed, 4 skipped |
| tools | 3812 passed, 4 skipped |
| field-agent | 207 passed |
| agent-registry | 311 passed |
| attestation-reporter | 264 passed |
| claude-approver | 315 passed |
| compliance-crosswalk | 369 passed, 5 skipped |
| conformance-sentinel | 263 passed |
| delegation-authority | 257 passed |
| federation-broker | 191 passed |
| force-gateway | 448 passed |
| incident-replay | 97 passed |
| kill-switch | 270 passed |
| lifecycle-manager | 269 passed |
| ops-console | 464 passed |
| spend-governor | 291 passed |

16 rows, 16 pass. 'No count went down' is NOT asserted: head is on an older main than the newest green GX10 log, so counts below that log (e.g. core 2350 vs 2398) are most likely base drift (MEDIUM). Landing needs 16/16 on the head rebased on current main.
Log: ~/ff-work/ver5p780-all.log on the GX10.
