# Verifier report: PR 527 (force-gateway /presets tests, P-23) full 16-suite run, head 9b21d9c

Verifier: gx10-verifier-2. Head tested: 9b21d9ce0f2ad661ce7b0b102ae7ed8b8b657ade (worktree ~/ff-work/wt-pr527v2). PR head at report time: 9b21d9ce0f2ad661ce7b0b102ae7ed8b8b657ade.
Run: full 16-suite run on the GX10, 07:33-07:51, Postgres port 55435, log ~/ff-work/pr527v2-all.log. Result: all 16 suites green, 0 failed.

| suite | result | vs main 97dcfec (my 06:36 run) |
|---|---|---|
| core+sealed-ledger | 2350 passed, 4 skipped | same |
| tools | 3801 passed, 4 skipped | main: 1 failed, 3800 passed |
| field-agent | 207 | same |
| agent-registry | 311 | same |
| attestation-reporter | 255 | same |
| claude-approver | 315 | same |
| compliance-crosswalk | 369, 5 skipped | same |
| conformance-sentinel | 263 | same |
| delegation-authority | 257 | same |
| federation-broker | 191 | same |
| force-gateway | 466 passed | +18 |
| incident-replay | 97 | same |
| kill-switch | 270 | same |
| lifecycle-manager | 269 | same |
| ops-console | 457 | same |
| spend-governor | 291 | same |

Baseline: main 97dcfec (report 20261104-1153). No suite count went down. force-gateway +18 matches the PR scope (new tests). The main C-57 proxy-lint failure is not present on this head (cause not diffed).
