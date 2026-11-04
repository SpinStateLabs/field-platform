# Verifier 4: PR584 @ 7007f9c (delegation-authority S-2-3; full 16-suite run, GX10) - 1 FAILURE, inherited from main
Head 7007f9c65c598fcbab6e2e445df63918f428c57c (equals open PR head at run start). Log: ~/ff-work/pr584-v4-all.log. HIGH confidence in counts.
- core+sealed-ledger 2350 passed, 4 skipped
- tools **1 failed**, 3800 passed, 4 skipped
- delegation-authority 263 passed (the PR's suite; 257 on unrelated heads, +6)
- field-agent 207; agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369 (5 skipped)
- conformance-sentinel 263; federation-broker 191; force-gateway 448; incident-replay 97
- kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291
Failure (C-57 file re-run alone, reproduced: 1 failed, 101 passed): tools/tests/test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist - "tools/start_role_session.py::call::urllib.request.urlopen x1". Not listed from the full run itself (MEDIUM it is the only one; count 1 matches).
Attribution (HIGH): diff vs main (97dcfec13, an ancestor) = delegation_authority/doa.py + test_doa_max_ttl_bound_s23.py only; start_role_session.py untouched. No count went down.
