# Verifier report: batch m2 (draft PR 794) @ 869cf2e — 16/16 GREEN

Head 869cf2ed76e73d69a8a89df0d0e2aa83984064c6 (= refs/heads/batch/2026-11-05-m2 = PR 794 head, at claim, in worktree, and at run end). Batch of PRs 643, 641, 638, 632, 630, 647 on aab217d (current main on GitHub at run end). GX10 ~/ff-work/pr794v1-all.log, 05:31-05:46 (runner idle, load 0.2 at start).

core+sealed-ledger 2411 passed, 4 skipped; tools 3817 passed, 4 skipped; field-agent 212; agent-registry 314; attestation-reporter 255; claude-approver 321; compliance-crosswalk 369 passed, 5 skipped; conformance-sentinel 271; delegation-authority 257; federation-broker 191; force-gateway 452; incident-replay 108; kill-switch 270; lifecycle-manager 269; ops-console 464; spend-governor 331.

0 failed, 0 errors. HIGH (counts from log).
Baseline: my main 3cede87 run (the last full run; I did not run aab217d itself). Up vs that: core +61, tools +5, field-agent +5, claude-approver +6, conformance-sentinel +8, force-gateway +4, incident-replay +11, spend-governor +40. Equal: the other 8 suites. Nothing went down. The comparison base differs from aab217d by whatever landed between 3cede87 and aab217d; MEDIUM on per-PR attribution (I did not map counts to individual PRs).
