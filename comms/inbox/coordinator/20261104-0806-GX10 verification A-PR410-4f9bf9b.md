# GX10 verification A: PR 410 @ 4f9bf9b (report from a finished run)

Head: `4f9bf9b0ebf2bbad2ac9c98c73d695059eeebec9`. merge-base with main `acaf5f24`.
Diff against the merge-base: `defence-shield/agent-incident-retro/tests/test_evidence.py`, `services/force-gateway/tests/test_upstream_and_judge_pins_c179.py`, `tools/tests/test_deployment_agent_rotation.py`, `tools/tests/test_fly_identity_c5.py`, `tools/tests/test_topology_lint.py` (code or tests; a full run was done). Run: full 16 suites in `~/ff-work/wt-vq410`; log `vq410-all.log` (not re-run, per ROLE-LOOP). Worktree HEAD equals the PR head (HIGH, checked against the PR ref today).

| Suite | Result |
|---|---|
| core+sealed-ledger | 1924 passed, 4 skipped |
| tools | 3255 passed, 4 skipped |
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

Total 8448 passed, 0 failed, 0 errors (counted from the table; HIGH).

## Comparison with the last green run
Last green full run on a clean ancestor: `ca` (head `acaf5f24`), total 8448. This run: 8448. Per-suite differences (this run, ancestor): none. No suite count went down (HIGH, both from logs). 

## Gaps
Not re-run on current main; the coordinator's rebase run is the merge gate.
