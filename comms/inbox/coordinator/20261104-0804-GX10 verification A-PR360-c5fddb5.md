# GX10 verification A: PR 360 @ c5fddb5 (report from a finished run)

Head: `c5fddb5459512135f9168ee899747a97858f046a`. merge-base with main `5808a5cd`.
Diff against the merge-base: `services/spend-governor/src/spend_governor/core.py`, `services/spend-governor/tests/test_burst_boundary_c128.py` (code or tests; a full run was done). Run: full 16 suites in `~/ff-work/wt-c360d-lane13`; log `c360d-lane13-all.log` (not re-run, per ROLE-LOOP). Worktree HEAD equals the PR head (HIGH, checked against the PR ref today).

| Suite | Result |
|---|---|
| core+sealed-ledger | 1865 passed, 4 skipped |
| tools | 3129 passed, 4 skipped |
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
| ops-console | 300 passed |
| spend-governor | 259 passed |

Total 8270 passed, 0 failed, 0 errors (counted from the table; HIGH).

## Comparison with the last green run
Last green full run on a clean ancestor: `c360c-lane13` (head `c876f6df`), total 8266. This run: 8270. Per-suite differences (this run, ancestor): [('spend-governor', 259, 255)]. No suite count went down (HIGH, both from logs). 

## Gaps
Not re-run on current main; the coordinator's rebase run is the merge gate.
