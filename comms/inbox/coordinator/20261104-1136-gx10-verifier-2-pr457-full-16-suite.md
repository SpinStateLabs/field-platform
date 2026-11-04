# Verifier report: PR 457 (C-1173 part 1) full 16-suite run, head 85fa7d1

Verifier: gx10-verifier-2. Head tested: 85fa7d15cb129cd35891e13ea2cd52e8e3d6f87c (worktree ~/ff-work/wt-pr457v2). PR head at report time: 85fa7d15cb129cd35891e13ea2cd52e8e3d6f87c.
Run: full 16-suite run on the GX10, 06:19-06:35, Postgres port 55435, log ~/ff-work/pr457v2-all.log. Result: all 16 suites green, 0 failed.

| suite | result | vs my PR 475 run (head 19d14a4) |
|---|---|---|
| core+sealed-ledger | 2346 passed, 4 skipped | same |
| tools | 3772 passed, 4 skipped | -4 |
| field-agent | 207 passed | same |
| agent-registry | 306 passed | -5 |
| attestation-reporter | 255 passed | same |
| claude-approver | 315 passed | same |
| compliance-crosswalk | 369 passed, 5 skipped | same |
| conformance-sentinel | 263 passed | same |
| delegation-authority | 256 passed | -1 |
| federation-broker | 188 passed | -3 |
| force-gateway | 448 passed | same |
| incident-replay | 97 passed | same |
| kill-switch | 242 passed | same |
| lifecycle-manager | 269 passed | same |
| ops-console | 457 passed | same |
| spend-governor | 291 passed | same |

Baseline: no same-base last-green run known to this verifier; PR 475 is the only comparison and is a different head. Four suites are lower than it (tools -4, agent-registry -5, delegation-authority -1, federation-broker -3). Cause not established; likely this branch lacking tests merged to main after its base (LOW-MEDIUM, base not diffed). Compare against this PR's merge-base before treating as a regression. No failures.
