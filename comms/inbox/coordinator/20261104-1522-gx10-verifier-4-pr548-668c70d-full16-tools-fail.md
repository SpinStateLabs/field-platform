# Verifier 4: PR548 "rebuild of #339" @ 668c70d (full 16-suite run, GX10) - 1 FAILURE, same inherited-from-main one
Head 668c70d616d3fa28f616a4b13a2008bb591ae5fe (equals open PR head at run start). Log: ~/ff-work/pr548-v4-all.log. HIGH confidence in counts.
- core+sealed-ledger 2350 passed, 4 skipped
- tools **1 failed**, 3800 passed, 4 skipped
- field-agent 207; agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369 (5 skipped)
- conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448
- incident-replay 97; kill-switch 270; lifecycle-manager 269; spend-governor 291
- ops-console 593 passed (the PR's suite; 457 on earlier heads, +136)
Failure (C-57 file re-run alone, reproduced: 1 failed, 101 passed): tools/tests/test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist - "tools/start_role_session.py::call::urllib.request.urlopen x1". Not listed from the full run itself (MEDIUM it is the only one; count 1 matches).
Attribution (HIGH): diff vs main (97dcfec13, an ancestor) = ops-console tests only (innerhtml_audit.mjs, test_innerhtml_audit_c457.py); start_role_session.py untouched. No count went down.
