# GX10 verifier ssl-ff-verifier-5: V-RUN-BATCH-m8-62c81c7

Verdict: **15/16 suites PASS, 1 FAIL (lifecycle-manager)** on head **62c81c761783b9807816160ebed0e4049937100e** (batch/2026-11-06-m8; no PR open for the branch at run time; m7 head e125a878 is an ancestor; checked-out HEAD == full SHA verified). HIGH.

| suite | result |
|---|---|
| core+sealed-ledger | 2533 passed, 4 skipped |
| tools | 4049 passed, 4 skipped |
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
| lifecycle-manager | **1 failed**, 286 passed |
| ops-console | 471 passed |
| spend-governor | 337 passed |

Failure: services/lifecycle-manager/tests/test_provision_alias_listed_require_g21.py::test_no_operators_row_is_shipped_in_this_repository_with_the_list_exemption: found ('docs/templates/operators.g17-template.json', 'don-breakglass'), expected none. Reproduced by a second run of the lifecycle-manager suite on the head: same single failure (HIGH).
Cause (MEDIUM, interaction between batch members, no fix run): that test exists on m7/main (it passed there: lifecycle-manager 287 passed on e125a878). Commit 5fb7be2 'G17: ten-row operators file template' in this batch adds docs/templates/operators.g17-template.json with operator rows including 'don-breakglass', which the G21 test scans for as a shipped operators row. Each PR passes alone; they fail combined. Fix is a builder/coordinator call: exempt the template path in the G21 test or rename/restructure the template; then re-run 16/16.
Every other suite equals or exceeds the m7 run (core 2533 vs 2524, tools 4049 vs 3986). Batch must not land on this head. Log: ~/ff-work/ver5m8-all.log on the GX10.
