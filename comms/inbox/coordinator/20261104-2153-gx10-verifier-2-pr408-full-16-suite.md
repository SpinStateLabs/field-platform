# Verifier report: PR 408 (public-safety follow-up to C-758) full 16-suite run, head 45a9bee — 16/16 green

Verifier: gx10-verifier-2. Head tested: 45a9bee473dc235b655b90f6405707071a3ac0ae (worktree ~/ff-work/wt-pr408v2). PR head at report time: 45a9bee473dc235b655b90f6405707071a3ac0ae. Merge-base acaf5f2 is an OLD base; origin/main is b963407.
Run: full 16-suite run on the GX10, 16:38-16:53, Postgres port 55435, log ~/ff-work/pr408v2-all.log. Result: all 16 suites green, 0 failed.

Counts: core+sealed-ledger 1924/4 skipped; tools 3279/5 skipped; field-agent 153; agent-registry 304; attestation-reporter 135; claude-approver 282; compliance-crosswalk 353/5 skipped; conformance-sentinel 260; delegation-authority 213; federation-broker 105; force-gateway 447; incident-replay 91; kill-switch 160; lifecycle-manager 224; ops-console 300; spend-governor 242.

Baseline: no run of mine on base acaf5f2. Compared with my PR 369 run (base 63e91b2, 20261104-2114): core +9, tools +149 (skipped 5 vs 4), all other suites equal; nothing lower. Different base, so not a regression check. Note tools skipped went 4 -> 5: one more skipped test than my other runs (cause not investigated; could be the base or this PR's file changes). Merge needs a rebase onto b963407; this result does not cover the merged state.
