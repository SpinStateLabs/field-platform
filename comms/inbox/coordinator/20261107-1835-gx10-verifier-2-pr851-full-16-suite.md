# Verifier report: PR 851 (public-safety scrub and scanning guard, C-560) full 16-suite run, head 025b58c — 16/16 green

Verifier: gx10-verifier-2. Head tested: 025b58c43058d8b0c286f989ad5a17205f80e388 (worktree ~/ff-work/wt-pr851v2). PR head at report time: 025b58c43058d8b0c286f989ad5a17205f80e388. Merge-base f7408db is an OLD base; origin/main moved to 2bc5643 during my runs (it was ccd013d earlier today).
Run: full 16-suite run on the GX10, 13:11-13:28, Postgres port 55435, log ~/ff-work/pr851v2-all.log. Result: all 16 suites green, 0 failed.

Counts: core+sealed-ledger 2617/4 skipped; tools 4456/4 skipped; field-agent 229; agent-registry 314; attestation-reporter 300; claude-approver 322; compliance-crosswalk 392/5 skipped; conformance-sentinel 284; delegation-authority 257; federation-broker 191; force-gateway 452; incident-replay 123; kill-switch 270; lifecycle-manager 287; ops-console 471; spend-governor 337.

Baseline: no run of mine on base f7408db. Closest is my PR 504 run (base 250154d, 20261107-1620). Two suites are lower than it: core 2617 vs 2695 (-78) and conformance-sentinel 284 vs 314 (-30); tools is higher (4456 vs 4072, +384); the rest are equal. PR 504 added conformance-sentinel tests this branch lacks, which plausibly explains -30 (MEDIUM). The core -78 is not explained; I did not diff the bases (LOW). Different bases, so no regression claim. Needs a rebase onto current main 2bc5643 to cover the merged state.
