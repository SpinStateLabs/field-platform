# GX10 verifier ssl-ff-verifier-5: V-RUN-BATCH-m3-3804d0b

Verdict: **16/16 suites PASS** (0 failed, 0 errors) on head **3804d0b900daf15a6ba4d22cc9f0d8f8bd5bd9ee** (batch/2026-11-05-m3, draft PR 799; base 869cf2ed confirmed ancestor of head). HIGH.

Run: GX10 ~/ff-work/wt-ver5m3 (checked-out HEAD == 3804d0b9 full SHA, verified), runbatch.sh ver5m3, load avg 0.45 at start. Head pushed to the GX10 bare repo as ref ver5/m3-3804d0b because the GX10 ffrepo origin cannot see PR refs.

| suite | result |
|---|---|
| core+sealed-ledger | 2458 passed, 4 skipped |
| tools | 3835 passed, 4 skipped |
| field-agent | 212 passed |
| agent-registry | 314 passed |
| attestation-reporter | 277 passed |
| claude-approver | 321 passed |
| compliance-crosswalk | 375 passed, 5 skipped |
| conformance-sentinel | 279 passed |
| delegation-authority | 257 passed |
| federation-broker | 191 passed |
| force-gateway | 452 passed |
| incident-replay | 123 passed |
| kill-switch | 270 passed |
| lifecycle-manager | 277 passed |
| ops-console | 464 passed |
| spend-governor | 331 passed |

16 rows, 16 pass. Compared with the newest fully green earlier GX10 log on the box (main-v3-all.log, older main, not the 869cf2ed base): no suite count went down (every count equal or higher; skips unchanged). MEDIUM, because the baseline is not the exact base 869cf2ed.
Log: ~/ff-work/ver5m3-all.log on the GX10.
