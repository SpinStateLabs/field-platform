# restock-needed: builder

`dispatch.sh next builder` returned EMPTY at 14:23 after builder-1 finished S3-1 to S3-11, S3-16, S3-17, S3-20, S3-22, S3-23 and S3-24 (S3-12 to S3-15, S3-18, S3-19, S3-21 were taken by other builders or not issued to me).

Open for the groomer: (1) the S3 scout file's remaining cards if any are unclaimed; (2) a main-red fix, which no one owns: tools/start_role_session.py (added in #532) trips tools/tests/test_http_env_proxy_lint_c57.py::test_the_repo_matches_the_allowlist, so tests (3.11/3.12/3.13/3.14) are red on ~15 builder PRs (561, 563, 568, 571-573, 576, 578-582, 584, and others). Proposed patch, not built: pass trust_env=False or urllib ProxyHandler({}) in start_role_session.call (the lint text names both), or add the allowlist line. Needs a builder item; I will take it if it is issued.

I am running the FALLBACK now (Lane 2: one service scan for a public function no test names) and will propose before building.
