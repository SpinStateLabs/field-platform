# GX10 verifier report: PR795 full 16-suite, FAIL (ssl-ff-verifier-6)

Head: 5dd1a2ac3162a5b9d8cfaa7af5b724dce7dedc58 (PR795, "field-mcp: pin that only the exact string "1" is consent for an external https base URL (reviewer Q-49 M42)"). Checked-out HEAD equals the item head (pull/795/head, worktree ~/ff-work/wt-ver6-pr795). Full runbatch.sh run. Not rebased on current main (merge-base with main aab217d3; main now 3804d0b9).

Result: 15/16 suites green, 1 suite RED. NOT a 16/16.

Failure (reproduced on a second run, deterministic, fails in 1.4 s with -x):
- tools: `tools/tests/test_boundary_echo_lint_c505.py::test_boundary_echo_scan_matches_allowlist`
  AssertionError: new site: services/field-mcp/src/field_mcp/server.py::_main::cli x1
  (test_boundary_echo_lint_c505.py:352). The PR adds the new service services/field-mcp (27 files); the boundary-echo lint finds one non-allowlisted echo site in `_main` / `cli` and the allowlist was not updated (or the site must be removed). Cause inferred from the assertion text and the diff scope; I did not edit the code (MEDIUM-HIGH).

| suite | result |
|---|---|
| core+sealed-ledger | 2398 passed, 4 skipped |
| tools | 1 failed, 3811 passed, 4 skipped |
| field-agent | 212 passed |
| agent-registry | 314 passed |
| attestation-reporter | 255 passed |
| claude-approver | 321 passed |
| compliance-crosswalk | 369 passed, 5 skipped |
| conformance-sentinel | 263 passed |
| delegation-authority | 257 passed |
| federation-broker | 191 passed |
| force-gateway | 448 passed |
| incident-replay | 108 passed |
| kill-switch | 270 passed |
| lifecycle-manager | 269 passed |
| ops-console | 464 passed |
| spend-governor | 303 passed |

Totals counted from the table: 15 green, 1 red (1 failed test), 0 errors. field-mcp's own suite is not part of the 16-suite runbatch.sh set, so it was not exercised here (the runner has no field-mcp line).
Other counts differ from the common-base heads (core 2398, field-agent 212, claude-approver 321, incident-replay 108, spend-governor 303, agent-registry 314) because this branch carries a different base and the PR's added tests; no other failure.
Builder action: add the `_main::cli` echo site to the allowlist with justification, or fix the site; then request a re-verify on the new head.
