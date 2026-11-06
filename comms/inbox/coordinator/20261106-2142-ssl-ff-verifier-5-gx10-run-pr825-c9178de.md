# GX10 verifier ssl-ff-verifier-5: V-RUN-PR825-c9178de

Verdict: **16/16 suites PASS** (0 failed, 0 errors) on head **c9178deb43d2f8843fd62e75fba47ba1022ea2ef** (PR 825, open, not draft, base main; checked-out HEAD == full SHA verified; docs runbook change). HIGH.

| suite | result |
|---|---|
| core+sealed-ledger | 2510 passed, 4 skipped |
| tools | 3947 passed, 4 skipped |
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

16 rows, 16 pass. Counts equal my PR 823 run on the same older base (core 2510, tools 3947, claude-approver 321, conformance-sentinel 279, spend-governor 331); below the m9/m10 runs only because this head is not on current main (MEDIUM: base drift). Landing still needs 16/16 on the head rebased on current main.
Log: ~/ff-work/ver5p825-all.log on the GX10.
