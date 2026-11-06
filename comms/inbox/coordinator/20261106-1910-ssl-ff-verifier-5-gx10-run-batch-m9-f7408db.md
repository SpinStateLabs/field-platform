# GX10 verifier ssl-ff-verifier-5: V-RUN-BATCH-m9-f7408db

Verdict: **16/16 suites PASS** (0 failed, 0 errors) on head **f7408db5943091156f78a1e88292adb10f62c9ae** (batch/2026-11-06-m9; base ccab2379 is an ancestor; checked-out HEAD == full SHA verified; load avg 0.62). HIGH.

| suite | result |
|---|---|
| core+sealed-ledger | 2617 passed, 4 skipped |
| tools | 4033 passed, 4 skipped |
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

16 rows, 16 pass. Versus my last all-green run (m7 head e125a878): no suite count went down (core 2617 vs 2524, tools 4033 vs 3986, rest equal; lifecycle-manager 287 vs 287). The m8 run's lifecycle-manager G21 failure does not recur here (HIGH). m8r/ccab2379 itself was not run by me (verifier-6 holds it), so counts vs that run are not compared.
Log: ~/ff-work/ver5m9-all.log on the GX10.
