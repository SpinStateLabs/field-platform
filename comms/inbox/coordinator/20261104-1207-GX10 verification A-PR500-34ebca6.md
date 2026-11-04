# GX10 verification A: PR 500 @ 34ebca6 (report from a finished run)

Head: `34ebca6d03975a7d49433a2e83fcedd3fae4c2ea`. merge-base with main `cd3b7690`.
Diff against the merge-base: `docs/ENVIRONMENT.md`, `packages/field-core/src/field_core/ledger.py`, `packages/field-core/tests/test_ledger_non_finite_sa3.py`, `services/sealed-ledger/src/sealed_ledger/api.py`, `services/sealed-ledger/tests/test_append_non_finite_sa3.py` (code or tests; a full run was done). Run: full 16 suites in `~/ff-work/wt-vA500`; log `vA500-all.log` (not re-run, per ROLE-LOOP). Worktree HEAD equals the PR head (HIGH, checked against the PR ref today).

| Suite | Result |
|---|---|
| core+sealed-ledger | 2377 passed, 4 skipped |
| tools | 3801 passed, 4 skipped |
| field-agent | 207 passed |
| agent-registry | 311 passed |
| attestation-reporter | 255 passed |
| claude-approver | 315 passed |
| compliance-crosswalk | 369 passed, 5 skipped |
| conformance-sentinel | 263 passed |
| delegation-authority | 257 passed |
| federation-broker | 191 passed |
| force-gateway | 448 passed |
| incident-replay | 97 passed |
| kill-switch | 270 passed |
| lifecycle-manager | 269 passed |
| ops-console | 457 passed |
| spend-governor | 291 passed |

Total 10178 passed, 0 failed, 0 errors (counted from the table; HIGH).

## Comparison with the last green run
Last green full run on a clean ancestor: `batch-m1b` (head `cd3b7690`), total 10151. This run: 10178. Per-suite differences (this run, ancestor): [('core+sealed-ledger', 2377, 2350)]. No suite count went down (HIGH, both from logs). Run executed this session by runbatch.sh from the GitHub PR head in wt-vA500.

## Gaps
Not re-run on current main; the coordinator's rebase run is the merge gate.
