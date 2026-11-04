# Verifier 4: PR558 @ 00e18c2 (force-gateway drop counters; full 16-suite run, GX10) - 1 FAILURE, the known main C-57 lint (fixed on main, head not rebased)
Head 00e18c239225b99c3b80535b5c5404ad8e6deac5 (equals open PR head at run start). Log: ~/ff-work/pr558-v4-all.log. HIGH confidence in counts.
- core+sealed-ledger 2350 passed, 4 skipped
- tools **1 failed**, 3800 passed, 4 skipped
- force-gateway 455 passed (the PR's suite; 448 on main, +7)
- field-agent 207; agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369 (5 skipped)
- conformance-sentinel 263; delegation-authority 257; federation-broker 191; incident-replay 97
- kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291
Failure (single-file re-run, reproduced): tools/tests/test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist - "tools/start_role_session.py::call::urllib.request.urlopen x1". Not listed from the full run itself (MEDIUM it is the only one; count 1 matches).
Attribution (HIGH): merge-base 97dcfec13; the head is exactly 1 commit behind main, and that commit is b963407 (the fix for this lint). Diff vs main = force-gateway README, api.py, 1 new test file (+144/-10); start_role_session.py untouched. Rebasing on b963407 should clear it; I did not re-run after a rebase. No count went down.
