# Verifier report: PR 417 (ntfy alert titles pinned, C-84) full 16-suite run, head 3e53c52 — 16/16 green

Verifier: gx10-verifier-2. Head tested: 3e53c52b5ffb5c1d20c699586a468c1205be8448 (worktree ~/ff-work/wt-pr417v2). PR head at report time: 3e53c52b5ffb5c1d20c699586a468c1205be8448. Merge-base 4d0c331 is an OLD base; origin/main is b963407.
Run: full 16-suite run on the GX10, 16:54-17:09, Postgres port 55435, log ~/ff-work/pr417v2-all.log. Result: all 16 suites green, 0 failed.

Counts: core+sealed-ledger 1925/4 skipped; tools 3268/4 skipped; field-agent 153; agent-registry 304; attestation-reporter 135; claude-approver 282; compliance-crosswalk 354/5 skipped; conformance-sentinel 260; delegation-authority 213; federation-broker 105; force-gateway 447; incident-replay 91; kill-switch 160; lifecycle-manager 224; ops-console 300; spend-governor 242.

Baseline: no run of mine on base 4d0c331. Compared with my PR 408 run (base acaf5f2, 20261104-2153): core +1, compliance-crosswalk +1, tools -11 (3268 vs 3279, skipped 4 vs 5), all other suites equal. The tools drop is not attributable: different bases, and I did not diff (LOW). Reviewer/coordinator: if this PR should only add tests, compare tools against merge-base 4d0c331 before treating -11 as a regression. Merge needs a rebase onto b963407; this result does not cover the merged state.
