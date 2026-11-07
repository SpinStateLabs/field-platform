# Verifier report: PR 380 (field-mcp PR 2, Tier 2 write tools) full 16-suite run, head bc53026 — 16/16 green, but the PR's own package is not in the 16

Verifier: gx10-verifier-2. Head tested: bc53026e019c0ef5db09a82e9d992d371433d9ce (worktree ~/ff-work/wt-pr380v2). PR head at report time: bc53026e019c0ef5db09a82e9d992d371433d9ce. Merge-base 5808a5c is an OLD base; origin/main is ccd013d.
Run: full 16-suite run on the GX10, 10:45-10:59, load 1.0 at start, Postgres port 55435, log ~/ff-work/pr380v2-all.log. Result: all 16 suites green, 0 failed.

Counts: core+sealed-ledger 1865/4 skipped; tools 3129/4 skipped; field-agent 151; agent-registry 304; attestation-reporter 135; claude-approver 282; compliance-crosswalk 353/5 skipped; conformance-sentinel 256; delegation-authority 213; federation-broker 105; force-gateway 443; incident-replay 91; kill-switch 160; lifecycle-manager 224; ops-console 300; spend-governor 242.

Baseline: identical in all 16 suites to my PR 339 run on the same base 5808a5c (20261104-2041) except ops-console 300 vs 436 (PR 339 added ops-console tests). So nothing went down relative to the base.

CAVEAT (HIGH, from runbatch.sh): the 16-suite set does not include field-mcp. The write tools this PR adds (7 tools, separate write process) are therefore NOT exercised by this run; 16/16 says only that the existing suites are unaffected on the old base. Counts are far below main ccd013d (e.g. tools 3129 vs 4286) because of the old base. Needs a field-mcp test run (it needs its own venv per my notes) and a rebase onto ccd013d; this result does not cover the merged state.
