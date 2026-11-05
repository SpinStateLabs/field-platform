# Verifier report: batch m1a3 (batch/2026-11-04-m1a3, PRs 487 482 462 485 484 483) full 16-suite run, head aab217d — 16/16 green

Verifier: gx10-verifier-2. Head tested: aab217d3f002f162393cf488007fa6c70ed1fc6d (fetched from GitHub on the GX10 as branch m1a3v2, worktree ~/ff-work/wt-m1a3v2). Merge-base = origin/main tip = 3cede872e3285eac00e8b39d6cd1d3d01baad28f (both checked on the GX10 at 20:05), so this covers the merge target.
Run: full 16-suite run on the GX10, 20:05-20:21, Postgres port 55435, log ~/ff-work/m1a3v2-all.log. Result: all 16 suites green, 0 failed.

Counts: core+sealed-ledger 2398/4 skipped; tools 3812/4 skipped; field-agent 212; agent-registry 314; attestation-reporter 255; claude-approver 321; compliance-crosswalk 369/5 skipped; conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 108; kill-switch 270; lifecycle-manager 269; ops-console 464; spend-governor 303.

Baseline: I have no run of main 3cede87. Against my last main run b963407 (20261104-1630): core +48, tools +6, field-agent +5, agent-registry +3, claude-approver +6, incident-replay +11, ops-console +7, spend-governor +12, other 8 suites equal; nothing lower. Main moved from b963407 to 3cede87 in between, so the part of the delta from main itself is unknown (LOW). Against my batch m1b run (e4d7a77, 20261104-2250): similar, with tools 3812 vs 3810 and agent-registry 314 vs 311 higher and delegation-authority 257 vs 257 equal. No suite count went down vs either. No C-57 red.
