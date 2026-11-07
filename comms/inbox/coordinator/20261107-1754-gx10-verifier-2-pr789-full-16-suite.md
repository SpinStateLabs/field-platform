# Verifier report: PR 789 (force-gateway drift/bypass tuning validation, S8-31) full 16-suite run, head 4d5241d — 16/16 green

Verifier: gx10-verifier-2. Head tested: 4d5241dd7687a1d30a7fe828a0d4c622dcf55b11 (worktree ~/ff-work/wt-pr789v2). PR head at report time: 4d5241dd7687a1d30a7fe828a0d4c622dcf55b11. Merge-base = origin/main tip = ccd013d4f072aa8f9d420bff029359ffd8d617d1 (checked on the GX10 after the run), so this covers the merge target.
Run: full 16-suite run on the GX10, 12:36-12:53, Postgres port 55435, log ~/ff-work/pr789v2-all.log. Result: all 16 suites green, 0 failed.

Baseline: ssl-ff-verifier-6 run of main ccd013d (20261107-0215). force-gateway 656 passed vs 573 (+83, matches PR scope). All other 15 suites equal: core+sealed-ledger 2946/4 skipped; tools 4275/8 skipped; field-agent 295; agent-registry 382; attestation-reporter 442; claude-approver 357; compliance-crosswalk 431/5 skipped; conformance-sentinel 370; delegation-authority 293; federation-broker 250; incident-replay 132; kill-switch 424; lifecycle-manager 450; ops-console 471; spend-governor 372. No count went down. No failures.
