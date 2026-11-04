# Verifier report: PR 379 (deploy runbook scrub, C-607) full 16-suite run, head f958cab — 16/16 green

Verifier: gx10-verifier-2. Head tested: f958cab8afbd6579670f1aebee58eb050778a06f (worktree ~/ff-work/wt-pr379v2). PR head at report time: f958cab8afbd6579670f1aebee58eb050778a06f. Merge-base 63e91b2 is an OLD base (same as PR 369); origin/main is b963407.
Run: full 16-suite run on the GX10, 16:15-16:29, Postgres port 55435, log ~/ff-work/pr379v2-all.log. Result: all 16 suites green, 0 failed.

Counts: core+sealed-ledger 1878/4 skipped; tools 3130/4 skipped; field-agent 153; agent-registry 304; attestation-reporter 135; claude-approver 282; compliance-crosswalk 353/5 skipped; conformance-sentinel 260; delegation-authority 213; federation-broker 105; force-gateway 447; incident-replay 91; kill-switch 160; lifecycle-manager 224; ops-console 300; spend-governor 242.

Baseline: PR 369 run on the same base 63e91b2 (20261104-2114). Versus it, all 15 other suites are equal; core+sealed-ledger is 1878 vs 1915 (-37). PR 369 added core tests (+50) that this branch lacks, so a -37 against it is not by itself a regression, but I cannot attribute the 37 exactly and did not diff (LOW-MEDIUM). The change here is docs, so core should not move relative to the base; the base's own core count is not known to me. Merge needs a rebase onto b963407; this result does not cover the merged state.
