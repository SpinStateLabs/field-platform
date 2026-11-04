# Verifier 4: PR597 @ a3db18d (force-gateway CLI S-2-13; full 16-suite run, GX10) - 1 FAILURE, inherited from main
Head a3db18d5a3488125b8b2e9f434ad456871e2f4b4 (equals open PR head at run start). Log: ~/ff-work/pr597-v4-all.log. HIGH confidence in counts.
- core+sealed-ledger 2350 passed, 4 skipped
- tools **1 failed**, 3800 passed, 4 skipped
- force-gateway 473 passed (the PR's suite; 448 on unrelated heads, +25)
- field-agent 207; agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369 (5 skipped)
- conformance-sentinel 263; delegation-authority 257; federation-broker 191; incident-replay 97
- kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291
Failure (C-57 file re-run alone, reproduced: 1 failed, 101 passed): tools/tests/test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist - "tools/start_role_session.py::call::urllib.request.urlopen x1". Not listed from the full run itself (MEDIUM it is the only one; count 1 matches).
Attribution (HIGH): diff vs main (97dcfec13, an ancestor) = force_gateway/cli.py + test_cli_presets_telemetry.py only; start_role_session.py untouched. No count went down.
