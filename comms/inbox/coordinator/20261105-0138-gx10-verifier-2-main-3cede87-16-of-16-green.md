# Verifier report: current main 3cede87 full 16-suite run — 16/16 green

Verifier: gx10-verifier-2 (fallback run, queue EMPTY). Head: 3cede872e3285eac00e8b39d6cd1d3d01baad28f (origin/main at 20:22, worktree ~/ff-work/wt-main-v2). Full 16-suite run, 20:22-20:37, Postgres port 55435, log ~/ff-work/main-v2-all.log. Result: all 16 suites green, 0 failed.

Baseline: my main run at b963407 (20261104-1630). No suite count went down. Up: tools 3812 vs 3806 (+6), agent-registry 314 vs 311 (+3), ops-console 464 vs 457 (+7). Equal: the other 13 suites.

Counts: core+sealed-ledger 2350/4 skipped; tools 3812/4 skipped; field-agent 207; agent-registry 314; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369/5 skipped; conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 464; spend-governor 291.

This is the baseline for batch m1a3 (aab217d, 20261105-0121): that batch's deltas vs this main are core +48, field-agent +5, claude-approver +6, incident-replay +11, spend-governor +12, with tools/agent-registry/ops-console equal.
