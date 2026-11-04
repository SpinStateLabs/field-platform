# GX10 verification A: PR 573 @ 9a7dbab (report from a finished run)

Head: `9a7dbab6c677b21a5f050ebd742cf5731d081904`. merge-base with main `97dcfec1`.
Diff against the merge-base: `services/federation-broker/src/federation_broker/cli.py`, `services/federation-broker/tests/test_cli_per_request_headers_c1181.py` (code or tests; a full run was done). Run: full 16 suites in `~/ff-work/wt-vA573`; log `vA573-all.log` (not re-run, per ROLE-LOOP). Worktree HEAD equals the PR head (HIGH, checked against the PR ref today).

| Suite | Result |
|---|---|
| core+sealed-ledger | 2350 passed, 4 skipped |
| tools | 3800 passed, 4 skipped |
| field-agent | 207 passed |
| agent-registry | 311 passed |
| attestation-reporter | 255 passed |
| claude-approver | 315 passed |
| compliance-crosswalk | 369 passed, 5 skipped |
| conformance-sentinel | 263 passed |
| delegation-authority | 257 passed |
| federation-broker | 193 passed |
| force-gateway | 448 passed |
| incident-replay | 97 passed |
| kill-switch | 270 passed |
| lifecycle-manager | 269 passed |
| ops-console | 457 passed |
| spend-governor | 291 passed |

Total 10152 passed, 0 failed, 0 errors (counted from the table; HIGH).

## Comparison with the last green run
Last green full run on a clean ancestor: `main-v2` (head `97dcfec1`), total 10150. This run: 10152. Per-suite differences (this run, ancestor): [('federation-broker', 193, 191)]. No suite count went down (HIGH, both from logs). Run executed this session by runbatch.sh from the GitHub PR head in wt-vA573.

## Gaps
Not re-run on current main; the coordinator's rebase run is the merge gate.
