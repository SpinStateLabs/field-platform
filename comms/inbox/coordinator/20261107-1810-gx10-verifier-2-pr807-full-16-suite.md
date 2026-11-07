# Verifier report: PR 807 (FederationClient.cross tests, PR 764 conditions) full 16-suite run, head 7c1c7d2 — 16/16 green

Verifier: gx10-verifier-2. Head tested: 7c1c7d254dc79989df1250c55867f6d59e6051f8 (worktree ~/ff-work/wt-pr807v2). PR head at report time: 7c1c7d254dc79989df1250c55867f6d59e6051f8. Merge-base 078967e is an OLD base; origin/main is ccd013d.
Run: full 16-suite run on the GX10, 12:54-13:10, Postgres port 55435, log ~/ff-work/pr807v2-all.log. Result: all 16 suites green, 0 failed.

Counts: core+sealed-ledger 2350/4 skipped; tools 3812/4 skipped; field-agent 232; agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369/5 skipped; conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 464; spend-governor 291.

Baseline: no run of mine on base 078967e. Closest is my main 3cede87 run (20261105-0138, an older main): equal in 12 suites, field-agent 232 vs 207 (+25, plausibly this PR's tests), agent-registry 311 vs 314 (-3, cause not established; the base may sit before a change that main 3cede87 has, not diffed, LOW). Versus main ccd013d every suite is lower or equal (core 2350 vs 2946, tools 3812 vs 4275) because this base is far behind. Nothing failed. Needs a rebase onto ccd013d to cover the merged state.
