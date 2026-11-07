# GX10 verifier ssl-ff-verifier-5: FALLBACK full run on current main ccd013d4

Verdict: **16/16 suites PASS** (0 failed, 0 errors) on main **ccd013d4f072aa8f9d420bff029359ffd8d617d1** (origin/main at run time = batch m14 head; checked-out HEAD == full SHA verified; load avg 0.56). HIGH. No verifier card was unclaimed (dispatch.sh level: verifier 0), so this is the ROLE-LOOP fallback. It repeats the tree that ssl-ff-verifier-6 holds the m14 row for; no run of mine is claimed against that row.

| suite | result |
|---|---|
| core+sealed-ledger | 2946 passed, 4 skipped |
| tools | 4275 passed, 8 skipped |
| field-agent | 295 passed |
| agent-registry | 382 passed |
| attestation-reporter | 442 passed |
| claude-approver | 357 passed |
| compliance-crosswalk | 431 passed, 5 skipped |
| conformance-sentinel | 370 passed |
| delegation-authority | 293 passed |
| federation-broker | 250 passed |
| force-gateway | 573 passed |
| incident-replay | 132 passed |
| kill-switch | 424 passed |
| lifecycle-manager | 450 passed |
| ops-console | 471 passed |
| spend-governor | 372 passed |

16 rows, 16 pass. Versus my m13 run (ff06b339): no count went down (core 2946 vs 2929, tools 4275 vs 4249, attestation-reporter 442 vs 366, rest equal) (HIGH). tools skips 8 = 4 Windows-PowerShell + 4 empty-list. Log: ~/ff-work/ver5mainfb-all.log on the GX10.
