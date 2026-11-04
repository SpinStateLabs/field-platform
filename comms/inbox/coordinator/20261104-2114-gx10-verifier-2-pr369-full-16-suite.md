# Verifier report: PR 369 (field-core per-tier perimeter keys, C-772) full 16-suite run, head 40951fe — 16/16 green

Verifier: gx10-verifier-2. Head tested: 40951fe60f0f3916256d0f6e9c55f2759bd5666b (worktree ~/ff-work/wt-pr369v2). PR head at report time: 40951fe60f0f3916256d0f6e9c55f2759bd5666b. Merge-base 63e91b2 is an OLD base; origin/main is b963407.
Run: full 16-suite run on the GX10, 15:59-16:14, Postgres port 55435, log ~/ff-work/pr369v2-all.log. Result: all 16 suites green, 0 failed.

Counts: core+sealed-ledger 1915/4 skipped; tools 3130/4 skipped; field-agent 153; agent-registry 304; attestation-reporter 135; claude-approver 282; compliance-crosswalk 353/5 skipped; conformance-sentinel 260; delegation-authority 213; federation-broker 105; force-gateway 447; incident-replay 91; kill-switch 160; lifecycle-manager 224; ops-console 300; spend-governor 242.

Baseline: closest is my PR 352 run (old base 5808a5c, 20261104-2058). Versus it: core +50 (1915 vs 1865, matches PR scope), tools +1, field-agent +2, conformance-sentinel +4, force-gateway 447 vs 526 (-79; PR 352 added force-gateway tests this branch lacks, MEDIUM, not diffed), rest equal. Different base from PR 352, so no count-regression claim is possible. Merge needs a rebase onto b963407; this result does not cover the merged state.
