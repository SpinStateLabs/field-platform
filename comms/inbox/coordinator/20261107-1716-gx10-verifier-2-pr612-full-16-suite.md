# Verifier report: PR 612 (rebuild of #465) full 16-suite run, head b0cc125 — 16/16 green, base one batch behind main

Verifier: gx10-verifier-2. Head tested: b0cc125813400342ccb2670dab4c135656e72b48 (worktree ~/ff-work/wt-pr612v2). PR head at report time: b0cc125813400342ccb2670dab4c135656e72b48. Merge-base ff06b339 is main before batch m14; origin/main is ccd013d (one batch ahead).
Run: full 16-suite run on the GX10, 11:58-12:15, Postgres port 55435, log ~/ff-work/pr612v2-all.log. Result: all 16 suites green, 0 failed. (My first start was blocked by a hook timeout; the run started 11:58 and is a single clean run.)

Counts: core+sealed-ledger 2929/4 skipped; tools 4249/8 skipped; field-agent 295; agent-registry 382; attestation-reporter 366; claude-approver 357; compliance-crosswalk 431/5 skipped; conformance-sentinel 370; delegation-authority 293; federation-broker 250; force-gateway 573; incident-replay 132; kill-switch 424; lifecycle-manager 450; ops-console 471; spend-governor 372.

Baseline: ssl-ff-verifier-6 on main ccd013d (20261107-0215). Equal in 12 suites; lower in three: core 2929 vs 2946 (-17), tools 4249 vs 4275 (-26), attestation-reporter 366 vs 442 (-76). verifier-6's own note gives attestation-reporter 366 on m12b, and this head's base ff06b339 contains m12b/m13 but not m14, so the three gaps are consistent with m14's tests not being on this base (MEDIUM; not diffed). Nothing failed. Needs a rebase onto ccd013d to cover the merged state.
