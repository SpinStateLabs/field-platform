# GX10 verification A: PR 530 @ ba42b3b (report from a finished run)

Head: `ba42b3b9d185b8e8fe0385b947973cc3c80e8db3`. merge-base with main `cd3b7690`.
Diff against the merge-base: `services/federation-broker/src/federation_broker/api.py`, `services/federation-broker/src/federation_broker/engine.py`, `services/federation-broker/tests/test_ledger_append_dropped_sc9.py` (code or tests; a full run was done). Run: full 16 suites in `~/ff-work/wt-vA530`; log `vA530-all.log` (not re-run, per ROLE-LOOP). Worktree HEAD equals the PR head (HIGH, checked against the PR ref today).

| Suite | Result |
|---|---|
| core+sealed-ledger | 2350 passed, 4 skipped |
| tools | 3801 passed, 4 skipped |
| field-agent | 207 passed |
| agent-registry | 311 passed |
| attestation-reporter | 255 passed |
| claude-approver | 315 passed |
| compliance-crosswalk | 369 passed, 5 skipped |
| conformance-sentinel | 263 passed |
| delegation-authority | 257 passed |
| federation-broker | 199 passed |
| force-gateway | 448 passed |
| incident-replay | 97 passed |
| kill-switch | 270 passed |
| lifecycle-manager | 269 passed |
| ops-console | 457 passed |
| spend-governor | 291 passed |

Total 10159 passed, 0 failed, 0 errors (counted from the table; HIGH).

## Comparison with the last green run
Last green full run on a clean ancestor: `batch-m1b` (head `cd3b7690`), total 10151. This run: 10159. Per-suite differences (this run, ancestor): [('federation-broker', 199, 191)]. No suite count went down (HIGH, both from logs). Run executed this session by runbatch.sh from the GitHub PR head in wt-vA530.

## Gaps
Not re-run on current main; the coordinator's rebase run is the merge gate.
