# GX10 verifier ssl-ff-verifier-5: V-RUN-PR798-ba1d32b

Verdict: **15/16 suites PASS, 1 FAIL (tools)** on head **ba1d32b618a0682a2f80f4894672cdbe58eaa30d** (PR 798, draft, base main; merge-base with main aab217d3; checked-out HEAD == full SHA verified). HIGH.

| suite | result |
|---|---|
| core+sealed-ledger | 2398 passed, 4 skipped |
| tools | **1 failed**, 4181 passed, 4 skipped |
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

Failure: tools/tests/test_boundary_echo_lint_c505.py::test_boundary_echo_scan_matches_allowlist: 'new site: tools/compose_resolved_check.py::main::cli x1'. Reproduced by a second full tools run on the head: same single failure (HIGH).
Likely cause (MEDIUM, not proven by a fix run): this PR edits tools/compose_resolved_check.py (diff vs main: that file, compose_bind_rules.py, the runbook and compose test files); the head's main() has CLI prints that echo exception type names (lines ~322 and ~331: 'could not read the model ({type(exc).__name__})' and 'shape this tool does not know'), and the boundary-echo allowlist in test_boundary_echo_lint_c505.py has no entry for compose_resolved_check.py. Not a base-drift failure: I found no commit on current main touching that lint or file that would fix it. Fix is the builder's: allowlist the site or drop the echo; then re-run.
Landing blocked on this head until fixed and re-run 16/16. Log: ~/ff-work/ver5p798-all.log on the GX10.
