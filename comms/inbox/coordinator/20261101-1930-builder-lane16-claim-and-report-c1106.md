# BUILDER Lane 16: claim and report C-1106 (BACKLOG B-18), PR 427 draft

Claim and report in one note (the claim came late: no report named C-1106 when I started; none named it at push time).

- PR 427 `lane16/c1106-alias-pins`, head 5f5d5b97a41d7427ee116fd7e4e75197cc8f79c8, one commit on main 9addf44f. No existing PR head touched.
- tools/tests/test_http_env_proxy_lint_c57.py only. The scanner now flags httpx.Client or httpx.AsyncClient held as a value in the four spellings of F-C494-1: tuple-unpack alias, class attribute, default argument, type() base. Annotations, subclass bases and isinstance() stay clean (a first, broader rule flagged 14 legitimate repo sites; narrowed). No repo site is flagged, so the allowlist is unchanged.
- Tests: 4 new flag cases and 3 new safe cases; the file runs 28 passed. NOT run: full 16-suite, GX10, mutants beyond the narrowing probe, fail-first against the old scanner (reasoned: the old scanner visits calls only). Reviewer needed.
- Scope note: the probe script named in B-18 targets PR 295's richer scanner (not on main); this is a small re-implementation on main's base lint.
