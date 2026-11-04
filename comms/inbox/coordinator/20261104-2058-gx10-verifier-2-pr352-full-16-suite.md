# Verifier report: PR 352 (force-gateway numeric tunables, C-582/C-623) full 16-suite run, head 6f30657 — 16/16 green

Verifier: gx10-verifier-2. Head tested: 6f3065793aa7dceb345ed746e7568036062d0e08 (worktree ~/ff-work/wt-pr352v2). PR head at report time: 6f3065793aa7dceb345ed746e7568036062d0e08. Merge-base 5808a5c is an OLD base; origin/main is b963407.
Run: full 16-suite run on the GX10, 15:43-15:57, Postgres port 55435, log ~/ff-work/pr352v2-all.log. Result: all 16 suites green, 0 failed.

Counts: core+sealed-ledger 1865/4 skipped; tools 3129/4 skipped; field-agent 151; agent-registry 304; attestation-reporter 135; claude-approver 282; compliance-crosswalk 353/5 skipped; conformance-sentinel 256; delegation-authority 213; federation-broker 105; force-gateway 526; incident-replay 91; kill-switch 160; lifecycle-manager 224; ops-console 300; spend-governor 242.

Baseline: same old base 5808a5c as my PR 339 run (20261104-2041). Versus it: force-gateway 526 vs 443 (+83, matches PR scope), ops-console 300 vs 436 (-136), all other suites equal. The ops-console drop is most likely PR 339's added tests not being in this branch (PR 339 is about ops-console tests), not a removal here (MEDIUM; not diffed). Merge needs a rebase onto b963407; this result does not cover the merged state. C-57 lint red absent (old base).
