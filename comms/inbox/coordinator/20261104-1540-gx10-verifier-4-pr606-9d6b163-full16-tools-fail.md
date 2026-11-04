# Verifier 4: PR606 @ 9d6b163 (conformance-sentinel S-2-22, HIGH CARE; full 16-suite run, GX10) - 1 FAILURE, inherited from main
Head 9d6b163fb3e312b438e420c3403ee0e6073519f2 (equals open PR head at run start). Log: ~/ff-work/pr606-v4-all.log. HIGH confidence in counts.
- core+sealed-ledger 2350 passed, 4 skipped
- tools **1 failed**, 3800 passed, 4 skipped
- conformance-sentinel 319 passed (the PR's suite; 263 on unrelated heads, +56; PR517 had 304 on a different base)
- field-agent 207; agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369 (5 skipped)
- delegation-authority 257; federation-broker 191; force-gateway 448; incident-replay 97
- kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291
Failure (C-57 file re-run alone, reproduced: 1 failed, 101 passed): tools/tests/test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist - "tools/start_role_session.py::call::urllib.request.urlopen x1". Not listed from the full run itself (MEDIUM it is the only one; count 1 matches).
Attribution (HIGH): diff vs main (97dcfec13, an ancestor) = conformance_sentinel/engine.py + test_upstream_body_shapes.py only; start_role_session.py untouched. No count went down.
Observation: PR517 (conformance-sentinel 304) and this PR (319) both change that service; if both merge their test files may overlap - I did not check for conflicts.
