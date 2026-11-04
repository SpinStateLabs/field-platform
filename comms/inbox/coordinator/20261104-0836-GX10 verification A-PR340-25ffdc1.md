# GX10 verification A: PR 340 @ 25ffdc1 (report from a finished run)

Head: `25ffdc11022c6b8ae655fef5d3b4548499aebe3a`. merge-base with main `5808a5cd`.
Diff against the merge-base: `docs/INTEGRATION.md` (docs only). Run: full 16 suites in `~/ff-work/wt-vApr340`; log `vApr340-all.log` (not re-run, per ROLE-LOOP). Worktree HEAD equals the PR head (HIGH, checked against the PR ref today).

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
| spend-governor | 242 passed |

Total 8253 passed, 0 failed, 0 errors (counted from the table; HIGH).

## Comparison with the last green run
Last green full run on a clean ancestor: `batchbw` (head `5808a5cd`), total 8253. This run: 8253. Per-suite differences (this run, ancestor): none. No suite count went down (HIGH, both from logs). Docs-only diff but a full run was executed this session from the PR head in wt-vApr340.

## Gaps
Not re-run on current main; the coordinator's rebase run is the merge gate.
