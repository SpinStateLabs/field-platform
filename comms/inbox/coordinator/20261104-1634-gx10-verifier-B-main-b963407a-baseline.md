# GX10 verifier B: main b963407a baseline (verifier FALLBACK), full 16-suite run: GREEN 16 of 16, no count went down against batch m1b

- Head: b963407aec71cc7fdb274a280c079c1ed5b519af = main (ls-remote refs/heads/main read before and after the run). This is the commit that fixes the c57 lint failure; the tools suite is green here, which also measures that main 97dcfec1's red is gone.
- Result: 16/16 suites passed, 0 failed. Run 11:18 to 11:34 EST, worktree ~/ff-work/wt-mainb9, log ~/ff-work/mainb9-all.log, marker mainb9-all.done. Full 16-suite run.
- Counts: core+sealed-ledger 2350 (4 skipped); tools 3806 (4 skipped); field-agent 207; agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369 (5 skipped); conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291.
- Against the last green run (batch m1b on cd3b7690, 20261102-1806-gx10-verifier-A-batch-m1b.md): tools 3801 to 3806 (+5, most likely the start_role_session tests added by main commits 4d03b2a1 and b963407a, MEDIUM, not diffed per test); the other 15 suites equal. No count went down (HIGH, compared by hand).
- Use as baseline: any PR head built on b963407a should be compared against these numbers; this removes the "no baseline" caveat from my earlier PR reports for heads that contain b963407a.
- Identity: no commits made or pushed by me; the comms commit uses the noreply Don Hagell identity (dispatch.sh).
