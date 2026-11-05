# Verifier report: PR 656 (FieldClient base_url scheme check, S4-8) full 16-suite run, head dc312fd — 16/16 green

Verifier: gx10-verifier-2. Head tested: dc312fda23feb9e1051180e953f14bd68dcb3b7f (worktree ~/ff-work/wt-pr656v2). PR head at report time: dc312fda23feb9e1051180e953f14bd68dcb3b7f. Merge-base = origin/main tip = b963407 (checked on the GX10), so this covers the merge target.
Run: full 16-suite run on the GX10, 18:58-19:14, Postgres port 55435, log ~/ff-work/pr656v2-all.log. Result: all 16 suites green, 0 failed.

Baseline: main b963407 (my 11:14 run, report 20261104-1630). field-agent 238 passed (+31, matches PR scope); all other 15 suites equal to main: core+sealed-ledger 2350/4 skipped; tools 3806/4 skipped; agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369/5 skipped; conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291. No count went down. No C-57 red.
