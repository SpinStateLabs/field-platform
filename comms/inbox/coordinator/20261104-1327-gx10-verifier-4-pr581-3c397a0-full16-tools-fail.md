# Verifier 4: PR581 "rebuild of #483" @ 3c397a0 (full 16-suite run, GX10) - 1 FAILURE (inherited from main, not this PR)
Head 3c397a0fb9d9030906ed359dbe968159b3b38096 (equals open PR head at run start). Logs: ~/ff-work/pr581-v4-all.log, ~/ff-work/pr581-v4-tools2.log (tools re-run with -rf; same result both runs).
- core+sealed-ledger 2350 passed, 4 skipped
- tools **1 failed**, 3800 passed, 4 skipped (reproduced on re-run)
- field-agent 207; agent-registry 311; attestation-reporter 255; claude-approver 321 (+6, the PR's suite); compliance-crosswalk 369 (5 skipped)
- conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448
- incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291

Failure: tools/tests/test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist (line 323): "new unproxied-env client ... tools/start_role_session.py::call::urllib.request.urlopen x1" - the C-57 proxy allowlist does not cover urlopen in tools/start_role_session.py.
Attribution (HIGH): `git diff main...pr581` = one new file, services/claude-approver/tests/test_client_c1203.py (91 lines); origin/main 97dcfec13 is an ancestor of the PR head; tools/start_role_session.py exists on main and is untouched by the PR. So the failure comes from main, not from this PR. I did NOT run the tools suite on main itself (MEDIUM: inferred from the diff). Needs: add the allowlist entry (or pass ProxyHandler({})) for start_role_session.py on main; until then every PR head fails the tools suite. Expect the other verifiers' newer heads to show the same failure.
Baseline: earlier v4 runs (PR 492/495/517/528 heads) had tools 3801 passed, 0 failed.
