# GX10 verification A: PR 379 @ f958cab (report from a finished run)

Head: `f958cab8afbd6579670f1aebee58eb050778a06f`. merge-base with main `63e91b21`.
Diff against the merge-base: `docs/runbooks/v1.2-deploy-rollback.md`, `tools/tests/test_deploy_docs.py` (code or tests; a full run was done). Run: full 16 suites in `~/ff-work/wt-vq379`; log `vq379-all.log` (not re-run, per ROLE-LOOP). Worktree HEAD equals the PR head (HIGH, checked against the PR ref today).

| Suite | Result |
|---|---|
| core+sealed-ledger | 1878 passed, 4 skipped |
| tools | 3130 passed, 4 skipped |
| field-agent | 153 passed |
| agent-registry | 304 passed |
| attestation-reporter | 135 passed |
| claude-approver | 282 passed |
| compliance-crosswalk | 353 passed, 5 skipped |
| conformance-sentinel | 260 passed |
| delegation-authority | 213 passed |
| federation-broker | 105 passed |
| force-gateway | 447 passed |
| incident-replay | 91 passed |
| kill-switch | 160 passed |
| lifecycle-manager | 224 passed |
| ops-console | 300 passed |
| spend-governor | 242 passed |

Total 8277 passed, 0 failed, 0 errors (counted from the table; HIGH).

## Comparison with the last green run
Last green full run on a clean ancestor: `batchbx` (head `63e91b21`), total 8277. This run: 8277. Per-suite differences (this run, ancestor): none. No suite count went down (HIGH, both from logs). 

## Gaps
Not re-run on current main; the coordinator's rebase run is the merge gate.
