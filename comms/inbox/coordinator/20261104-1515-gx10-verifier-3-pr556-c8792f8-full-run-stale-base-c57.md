# Verifier 3: full 16-suite run, PR 556 "rebuild of #372" head c8792f8 (field-agent C-855 + upstream-error tests): 15/16, tools 1 failure = c57 lint, stale base
Head c8792f8470264bada26ec17a3581f69cef9059c1 (equals open PR head at run start). At the end main is b963407 (has the PR546 c57 fix); this head is 1 commit behind it (HIGH). GX10 ~/ff-work/wt-pr556-v3, log ~/ff-work/pr556-v3-all.log. Full 16-suite run.
- tools: 1 failed, 3800 passed, 4 skipped. Isolated test_http_env_proxy_lint_c57.py: 1 failed, 101 passed (same single failure; name not read from the full-run log; MEDIUM). Same cause as PR587/576/616/609/563. The PR diff (11 files) touches field-core/field-agent/conformance-sentinel tests and src, not tools.
- Action: rebase onto b963407, re-run tools; not re-run, not verified green.
- core+sealed-ledger 2354 passed, 4 skipped (+4 vs 2350; this PR's tests); field-agent 258 passed, 1 skipped (+51 vs 207, 1 new skip); 
- agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369 (5 skipped); conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291
Note (LOW): the new field-agent skip is unexplained; I did not look at which test skips.
No TEST_DATABASE_URL set by runbatch.sh.
