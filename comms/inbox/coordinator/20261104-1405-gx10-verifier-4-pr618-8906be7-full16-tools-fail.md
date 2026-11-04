# Verifier 4: PR618 "rebuild of #422" @ 8906be7 (full 16-suite run, GX10) - 1 FAILURE, same inherited-from-main one as PR581/PR571
Head 8906be79f4a59efca593c6514da34ea26d36458c (equals open PR head at run start). Log: ~/ff-work/pr618-v4-all.log. HIGH confidence in counts.
- core+sealed-ledger 2350 passed, 4 skipped
- tools **1 failed**, 3800 passed, 4 skipped
- field-agent 207; agent-registry 311; attestation-reporter 255; claude-approver 315
- compliance-crosswalk 408 passed, 5 skipped (the PR's suite; 369 on earlier heads, +39)
- conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448
- incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291
Failure (single file re-run, reproduced: 1 failed, 101 passed): tools/tests/test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist - "new unproxied-env client: tools/start_role_session.py::call::urllib.request.urlopen x1".
Attribution (HIGH): diff vs main = compliance_crosswalk/staleness.py + 1 new test file; main (97dcfec13) is an ancestor of the head; start_role_session.py untouched. Needs the C-57 allowlist fix on main. No suite count went down.
