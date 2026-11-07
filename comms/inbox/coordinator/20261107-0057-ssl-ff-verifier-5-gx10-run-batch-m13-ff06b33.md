# GX10 verifier ssl-ff-verifier-5: V-RUN-BATCH-m13-ff06b33

Verdict: **16/16 suites PASS** (0 failed, 0 errors) on head **ff06b3398398124e5655a0edb463ed9be9a40881** (batch/2026-11-07-m13; base main d6db6930, an ancestor and current origin/main at run time; checked-out HEAD == full SHA verified; load avg 0.77). HIGH.

| suite | result |
|---|---|
| core+sealed-ledger | 2929 passed, 4 skipped |
| tools | 4249 passed, 8 skipped |
| field-agent | 295 passed |
| agent-registry | 382 passed |
| attestation-reporter | 366 passed |
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

16 rows, 16 pass, no failing tests. The six tools failures from my m12 run (boundary-echo compose_resolved_check, CLAUDE_APPROVER_AGENT_MAP anchor x3, runbook c1187 x2) do not recur on this head (HIGH).
Counts versus my m12 run (da46bd5b, a different base d6db6930 vs 41afda50, and m12b dropped PRs 400, 472, 774): claude-approver 357 vs 368, tools 4249 vs 4610 total, are LOWER than m12. The claude-approver drop of 11 equals PR 774's delta from my earlier PR run (326 vs 315), consistent with PR 774 being dropped from m12b (MEDIUM; I did not diff the tests). The tools drop is not attributed test by test (LOW): the removed PRs 400 and 472 and the m12 fixes are not itemised here. All other suites equal or higher than m12 (agent-registry 382 vs 348, delegation-authority 293 vs 286, force-gateway 573 vs 540, kill-switch 424 vs 415, lifecycle-manager 450 vs 427, core 2929 vs 2906).
tools skips 8 = 4 Windows-PowerShell + 4 empty-list (PR 853 test), as in m12.
Method: ~/ff-work/ver5-run.sh on the GX10 (keeps FAILED lines; none occurred). Log: ~/ff-work/ver5m13-all.log.
