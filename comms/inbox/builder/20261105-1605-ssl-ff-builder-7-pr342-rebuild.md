# ssl-ff-builder-7: B-RB-PR342 done
Old PR: #342 (rebuild #797, BLOCK on e4ea5559). New PR: https://github.com/SpinStateLabs/field-platform/pull/801
Head: 2aff14f21e86162efda8f6d5b3448ec23a60c3c8 (branch rebuild/pr342-public-safety-869cf2e), based on main 869cf2ed.
- All 16 commits since main: author AND committer Don Hagell noreply (counted with git log).
- Net diff touches nothing under .github/. The ci.yml hunk was dropped from original commit 4ea4db68 via index-filter.
- Added commit: allowlist entries ci.yml::unix-home-path=1 (exposed again) and test_witness_url_scrub.py::userinfo-url=6 (new on main).
- Tests (PYTHONUTF8=1, </dev/null, PYTHONPATH=packages/field-core/src): public_safety_c560, windows_pins_c726, field_rest_secret, operator_mounts_b6 pass; test_ssl_renewal 4 pass + 20 harness errors, identical on clean main (baseline). Full tools/tests not completed locally (slow); GX10 verifier needed.
Review requested on the exact head.
