# Verifier report: PR 666 (compose_resolved_check refusal, S4-18) full 16-suite run, head 82b2411 — 16/16 green

Verifier: gx10-verifier-2. Head tested: 82b24112e276ce1c6fe7b8c74f0492efd6dfb821 (worktree ~/ff-work/wt-pr666v2). PR head at report time: 82b24112e276ce1c6fe7b8c74f0492efd6dfb821. Merge-base = origin/main tip = b963407 (checked on the GX10), so this covers the merge target.
Run: full 16-suite run on the GX10, 19:16-19:31, Postgres port 55435, log ~/ff-work/pr666v2-all.log. Result: all 16 suites green, 0 failed.

Baseline: main b963407 (my 11:14 run, report 20261104-1630). tools 3826 passed, 4 skipped (+20, matches PR scope); all other 15 suites equal to main: core+sealed-ledger 2350/4 skipped; field-agent 207; agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369/5 skipped; conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291. No count went down. No C-57 red.
