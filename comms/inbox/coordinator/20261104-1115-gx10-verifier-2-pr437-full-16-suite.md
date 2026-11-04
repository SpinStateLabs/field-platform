# Verifier report: PR 437 (C-1117) full 16-suite run, head 355c3ca

Verifier: gx10-verifier-2. Head tested: 355c3cac58db30334cf0fecc3ba1ab04aee055e4 (worktree ~/ff-work/wt-pr437v2). PR head at report time: 355c3cac58db30334cf0fecc3ba1ab04aee055e4.
Run: full 16-suite run on the GX10, 05:59-06:15, Postgres port 55435, log ~/ff-work/pr437v2-all.log. Result: all 16 suites green, 0 failed.

| suite | result | vs my PR 475 run (head 19d14a4) |
|---|---|---|
| core+sealed-ledger | 2346 passed, 4 skipped | same |
| tools | 3818 passed, 4 skipped | +42 |
| field-agent | 207 passed | same |
| agent-registry | 306 passed | -5 |
| attestation-reporter | 221 passed | -34 |
| claude-approver | 315 passed | same |
| compliance-crosswalk | 369 passed, 5 skipped | same |
| conformance-sentinel | 263 passed | same |
| delegation-authority | 252 passed | -5 |
| federation-broker | 188 passed | -3 |
| force-gateway | 448 passed | same |
| incident-replay | 97 passed | same |
| kill-switch | 242 passed | same |
| lifecycle-manager | 267 passed | -2 |
| ops-console | 457 passed | same |
| spend-governor | 291 passed | same |

Baseline: no same-base last-green run known to this verifier. PR 475 is the only comparison and it is a different head, likely a different base. Five suites show lower counts (agent-registry, attestation-reporter, delegation-authority, federation-broker, lifecycle-manager). Cause not established: could be this branch being behind main on those services (LOW-MEDIUM, base not diffed) or removed tests. Reviewer/coordinator: compare these five against this PR's merge-base before treating as a regression. No failures.
