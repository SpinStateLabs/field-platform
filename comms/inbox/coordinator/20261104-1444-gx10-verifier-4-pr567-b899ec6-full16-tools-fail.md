# Verifier 4: PR567 "rebuild of #420" @ b899ec6 (full 16-suite run, GX10) - 1 FAILURE, same inherited-from-main one
Head b899ec631422a0751c24cfdc00bd56ac325d5de1 (equals open PR head at run start). Log: ~/ff-work/pr567-v4-all.log. HIGH confidence in counts.
- core+sealed-ledger 2350 passed, 4 skipped
- tools **1 failed**, 3816 passed, 4 skipped (+16 vs 3800 on PR571/581/618: the PR's new test file test_renew_token_signing_pins_b14.py, all pass)
- field-agent 207; agent-registry 311; attestation-reporter 255; claude-approver 315; compliance-crosswalk 369 (5 skipped)
- conformance-sentinel 263; delegation-authority 257; federation-broker 191; force-gateway 448
- incident-replay 97; kill-switch 270; lifecycle-manager 269; ops-console 457; spend-governor 291
Failure (C-57 file re-run alone, reproduced: 1 failed, 101 passed): tools/tests/test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist - "tools/start_role_session.py::call::urllib.request.urlopen x1". Same message as PRs 581/571/618/613. I did not list the failing id from the full run itself (MEDIUM that it is the only one; the count of 1 matches).
Attribution (HIGH): diff vs main (97dcfec13, an ancestor of the head) = 1 new test file, 258 lines; start_role_session.py untouched. Fix belongs on main (C-57 allowlist). No count went down.
