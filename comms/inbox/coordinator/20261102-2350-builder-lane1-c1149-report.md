# Lane 1 report: C-1149 (B-19)
Draft PR 445, branch lint/auth-headers-outside-field-core-c1149, head 3d291ddb (two commits on main 05942b98). First push; resets reviewer and verifier gates.
- tools/tests/test_auth_headers_outside_core_c1149.py (27 tests) and tools/tests/auth_headers_allowlist.txt (33 keys, 40 uses, equal to the scan). C-57 shape: AST scan of non-test code outside packages/field-core/; call, value use, alias, module alias and star import are findings.
- Red first: commit 307b1cf0 has the test with a header-only allowlist (repo test red); commit 3d291ddb lists the sites.
- Mutant: a call appended to a spend-governor cli file turns the repo test red and names the function; restored. New-site and stale-entry cases pinned.
- Cross-check: the five other non-test files that mention the name hold it only in comments or docstrings.
- Run: the new file 27 passed (Windows). Not run: the 16-suite set; GX10 verifier on the final head. Production code unchanged.
- Follow-up (not done): migrating the 33 sites to the guarded auth shrinks the list (design 4.4); needs field-core GuardedOperatorAuth wiring per service.
