# Verifier report: PR 535 (conformance-sentinel clause tests, P-3) full 16-suite run, head 02be413 — 16/16 green

Verifier: gx10-verifier-2. Head tested: 02be413fe86be389133c5449d096cb2da919c64f (worktree ~/ff-work/wt-pr535v2). PR head at report time: 02be413fe86be389133c5449d096cb2da919c64f. Merge-base cd3b769; origin/main is b963407 (merge-base is behind main, base not diffed).
Run: full 16-suite run on the GX10, 17:16-17:32, Postgres port 55435, log ~/ff-work/pr535v2-all.log. Result: all 16 suites green, 0 failed.

| suite | result | vs main b963407 (my 11:14 run) |
|---|---|---|
| core+sealed-ledger | 2350 passed, 4 skipped | same |
| tools | 3801 passed, 4 skipped | -5 (main 3806) |
| field-agent | 207 | same |
| agent-registry | 311 | same |
| attestation-reporter | 255 | same |
| claude-approver | 315 | same |
| compliance-crosswalk | 369, 5 skipped | same |
| conformance-sentinel | 274 passed | +11 (matches PR scope) |
| delegation-authority | 257 | same |
| federation-broker | 191 | same |
| force-gateway | 448 | same |
| incident-replay | 97 | same |
| kill-switch | 270 | same |
| lifecycle-manager | 269 | same |
| ops-console | 457 | same |
| spend-governor | 291 | same |

Baseline: main b963407. One suite is lower: tools 3801 vs 3806 (-5). Not attributable to this PR: its merge-base cd3b769 predates main and main's tools count includes the PR 546 fix and any tests added since (MEDIUM; merge-base not diffed). My PR 502/515/527 runs on a similar-era base also showed tools 3801, which supports a base difference. A rebase onto b963407 would confirm; this result does not cover the merged state.
