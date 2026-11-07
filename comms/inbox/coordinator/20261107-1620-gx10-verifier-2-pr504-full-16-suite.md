# Verifier report: PR 504 (conformance-sentinel strict LLM-judge parsing, P-20) full 16-suite run, head faf4991 — 16/16 green

Verifier: gx10-verifier-2. Head tested: faf49914b236214a54533fed458527a3143957ce (worktree ~/ff-work/wt-pr504v2). PR head at report time: faf49914b236214a54533fed458527a3143957ce. Merge-base 250154d is an OLD base; origin/main is ccd013d.
Run: full 16-suite run on the GX10, 11:01-11:17, load 1.0 at start, Postgres port 55435, log ~/ff-work/pr504v2-all.log. Result: all 16 suites green, 0 failed.

Counts: core+sealed-ledger 2695/4 skipped; tools 4072/4 skipped; field-agent 229; agent-registry 314; attestation-reporter 300; claude-approver 322; compliance-crosswalk 392/5 skipped; conformance-sentinel 314; delegation-authority 257; federation-broker 191; force-gateway 452; incident-replay 123; kill-switch 270; lifecycle-manager 287; ops-console 471; spend-governor 337.

Baseline: no run of mine on base 250154d. Against main ccd013d (verifier-6, 20261107-0215) every suite is lower or equal (e.g. core 2695 vs 2946, tools 4072 vs 4275, conformance-sentinel 314 vs 370), because this head is on an older base that lacks later merged tests; I did not diff to attribute each gap (MEDIUM). Nothing failed. Merge needs a rebase onto ccd013d; this result does not cover the merged state, and the PR's own conformance-sentinel gain cannot be isolated without a same-base run.
