# Verifier 3: full 16-suite run, PR 594 head 8f8b982 (sealed-ledger witness JSONL newline-only split, S-2-10): 15/16, tools 1 failure = c57 lint, stale base
Head 8f8b982c1fb729adb3580d88690b4a5198f706aa (equals open PR head at run start). At run end main is b963407 (has the PR546 c57 fix); this head is 1 commit behind (HIGH). GX10 ~/ff-work/wt-pr594-v3, log ~/ff-work/pr594-v3-all.log. Full 16-suite run.
- tools: 1 failed, 3800 passed, 4 skipped. Isolated test_http_env_proxy_lint_c57.py: 1 failed, 101 passed (same single failure; name not read from the full-run log; MEDIUM). Same cause as PR587/576/616/609/563/556/605. PR diff = sealed_ledger/witness.py + new test_witness_events_line_split_s210.py only; not tools.
- Action: rebase onto b963407 and re-run tools; not re-run, not verified green.
- core+sealed-ledger 2365 passed, 4 skipped (+15 vs 2350; this PR's tests); field-agent 207
- agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369 (5 skipped); conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291
No TEST_DATABASE_URL set by runbatch.sh.
