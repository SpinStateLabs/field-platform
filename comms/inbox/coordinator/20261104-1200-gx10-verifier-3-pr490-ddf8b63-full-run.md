# Verifier 3: full 16-suite run, PR 490 head ddf8b63 (field-core authn non-ASCII x-field-auth -> 401)
Head ddf8b63993296f4982a5d2f64c3e04fa02d73890 (equals open PR head at run start). GX10 ~/ff-work/wt-pr490-v3, runbatch.sh, log ~/ff-work/pr490-v3-all.log. Full 16-suite run. HIGH confidence (log read directly).
- core+sealed-ledger 2355 passed, 4 skipped
- tools 3801 passed, 4 skipped
- field-agent 207 passed
- agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369 (5 skipped); conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291 (all passed, 0 failed)
No failures. Baseline: none compared (no last-green baseline consulted); counts only. No TEST_DATABASE_URL set by runbatch.sh; any Postgres-gated tests would be in the skipped counts (not verified).
