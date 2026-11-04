# Verifier report: PR 515 (attestation-reporter render_pdf stale PDF, P-17) full 16-suite run, head bd909a5

Verifier: gx10-verifier-2. Head tested: bd909a517e1612e79f746e3262a11569e905bf96 (worktree ~/ff-work/wt-pr515v2). PR head at report time: bd909a517e1612e79f746e3262a11569e905bf96.
Run: full 16-suite run on the GX10, 07:12-07:32, Postgres port 55435, log ~/ff-work/pr515v2-all.log. Result: all 16 suites green, 0 failed.

| suite | result | vs main 97dcfec (my 06:36 run) |
|---|---|---|
| core+sealed-ledger | 2350 passed, 4 skipped | same |
| tools | 3801 passed, 4 skipped | main: 1 failed, 3800 passed |
| field-agent | 207 | same |
| agent-registry | 311 | same |
| attestation-reporter | 265 passed | +10 |
| claude-approver | 315 | same |
| compliance-crosswalk | 369, 5 skipped | same |
| conformance-sentinel | 263 | same |
| delegation-authority | 257 | same |
| federation-broker | 191 | same |
| force-gateway | 448 | same |
| incident-replay | 97 | same |
| kill-switch | 270 | same |
| lifecycle-manager | 269 | same |
| ops-console | 457 | same |
| spend-governor | 291 | same |

Baseline: main 97dcfec (report 20261104-1153). No suite count went down. attestation-reporter +10 matches the PR scope. The C-57 proxy-lint failure seen on main (tools/start_role_session.py urlopen) is not present on this head (LOW, cause not diffed; possibly fixed upstream since).
