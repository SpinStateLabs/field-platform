# Verifier 3: full 16-suite run, PR 563 "rebuild of #419" head 665b51c (compliance-crosswalk Q-47): 15/16, tools 1 failure = c57 lint, stale base
Head 665b51ceaf19b51f845e0dd0ce1c7d7536c01e05 (equals open PR head at run start). At the end main is b963407 (has the PR546 c57 fix); this head is 1 commit behind it (HIGH). GX10 ~/ff-work/wt-pr563-v3, log ~/ff-work/pr563-v3-all.log. Full 16-suite run.
- tools: 1 failed, 3800 passed, 4 skipped. Isolated test_http_env_proxy_lint_c57.py: 1 failed, 101 passed (same single failure; name not read from the full-run log; MEDIUM). Same cause as PR587/576/616/609 (start_role_session.py unproxied urlopen, fixed on main by PR546). PR diff = compliance-crosswalk (textsafe.py, 2 new test files, 2 more), not tools.
- Action: rebase onto b963407, re-run tools; not re-run, not verified green.
- compliance-crosswalk 400 passed, 5 skipped (+31 vs 369 on other heads; this PR's tests)
- core+sealed-ledger 2350 passed, 4 skipped; field-agent 207
- agent-registry 311; attestation-reporter 255; claude-approver 315; conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291
No TEST_DATABASE_URL set by runbatch.sh.
