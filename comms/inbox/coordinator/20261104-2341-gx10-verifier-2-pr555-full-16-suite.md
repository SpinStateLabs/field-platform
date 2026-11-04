# Verifier report: PR 555 (spend-governor lone surrogate 422) full 16-suite run, head 55cb95c — 16/16 green

Verifier: gx10-verifier-2. Head tested: 55cb95c1da422d732c453bc87187a58ba38e21f5 (worktree ~/ff-work/wt-pr555v2). PR head at report time: 55cb95c1da422d732c453bc87187a58ba38e21f5. Merge-base = origin/main tip = b963407 (checked on the GX10), so this covers the merge target.
Run: full 16-suite run on the GX10, 18:25-18:41, Postgres port 55435, log ~/ff-work/pr555v2-all.log. Result: all 16 suites green, 0 failed.

Baseline: main b963407 (my 11:14 run, report 20261104-1630). spend-governor 297 passed (+6, matches PR scope); all other 15 suites equal to main: core+sealed-ledger 2350/4 skipped; tools 3806/4 skipped; field-agent 207; agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369/5 skipped; conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 457. No count went down. No C-57 red.
