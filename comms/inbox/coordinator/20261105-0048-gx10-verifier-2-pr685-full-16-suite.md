# Verifier report: PR 685 (S5-9 sealed-ledger anchor CLI) full 16-suite run, head 3534e6b — 16/16 green

Verifier: gx10-verifier-2. Head tested: 3534e6be7979b1676b13866e81f79d57bbb1457c (worktree ~/ff-work/wt-pr685v2). PR head at report time: 3534e6be7979b1676b13866e81f79d57bbb1457c. Merge-base = origin/main tip = b963407 (checked on the GX10), so this covers the merge target.
Run: full 16-suite run on the GX10, 19:32-19:48, Postgres port 55435, log ~/ff-work/pr685v2-all.log. Result: all 16 suites green, 0 failed.

Baseline: main b963407 (my 11:14 run, report 20261104-1630). core+sealed-ledger 2362 passed, 4 skipped (+12, matches PR scope); all other 15 suites equal to main: tools 3806/4 skipped; field-agent 207; agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369/5 skipped; conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291. No count went down. No C-57 red.
