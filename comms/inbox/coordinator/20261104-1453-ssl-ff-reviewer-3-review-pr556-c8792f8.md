# Review PR 556 @ c8792f8470264bada26ec17a3581f69cef9059c1 (rebuild of #372: SDK errors carry no upstream body, C-503 family) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head c8792f84. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head still required.

## Objections first
1. "Never the body" has several leak routes in Python, not one: the message text, `from exc`, implicit `__context__`, `JSONDecodeError.doc`, a pydantic `ValidationError` input repr. The PR's own comments say the `raise` sits outside the `except` for that reason. I attacked each route (B4, B6, F2, F8, L2, L4, U3, U6).
2. Relayed BLOCK explanations (federation) are deliberately kept, bounded and escaped: `_bounded` (300 chars, `ascii()`); a broker is semi-trusted. Whether 300 characters of a broker's reasons is acceptable is a design call; pinned by F3-F6.
3. The `.verdict` attribute keeps the whole upstream verdict on the exception (F7 pinned): anything that logs the exception object with its attributes would still print it; not in scope of this PR.

## Facts (HIGH)
- Head fetched via refs/pull/556/head = c8792f84; 3 commits; base origin/main 97dcfec1 (main has since moved one unrelated commit); author AND committer on all 3: Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 11 files, +482 -46: `field_agent` bootstrap/federation/liveness/usage, `field_core/errors.py` (`upstream_error` formats only a real int status), the sentinel CLI line, docs, and tests (`test_sdk_errors_c642.py` +259, others extended).
- Baselines unmutated, run from each package's own directory with relative paths: field-agent 257 passed, 1 skipped, 1 deselected; field-core `test_upstream_error_c503.py` 17 passed; sentinel `test_upstream_errors_c503.py` 4 passed. The one deselected test (`test_canary_agent.py::test_the_process_never_exits_on_a_halt`) FAILS on main as well and on the head (it launches a subprocess my environment cannot import field_agent into): an environment baseline failure, not counted. (A first run with the three suites in one pytest call had a collection-error baseline; all its "kills" were invalid and discarded; the tables below are from the corrected runs.)

## Mutants (all three suites each time; files restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| bootstrap: register reply must be an object, no body or exception text, raised outside the except; mint likewise (B1-B6) | 6 | 6 | 0 |
| federation: non-200 via `upstream_error`; no-verdict raised outside except (F2, F8); BLOCK reasons bounded 300, escaped, truncated, still bounded in the message, verdict kept (F1, F3-F7) | 9 | 9 | 0 |
| liveness: non-200 via `upstream_error`; unusable 200 raised outside the except, never None (L1, L2, L3, L4) | 4 | 4 | 0 |
| usage and spend: 404 and non-201 words not relayed; unusable 201 raises, never None (U1-U5) | 5 | 5 | 0 |
| usage and spend: unusable 201 error not chained (U6) | 1 | 0 | 1 (EQUIVALENT) |
| core `upstream_error` formats only a real int status (E1, E2, E3) | 3 | 3 | 0 |
| sentinel CLI does not echo the body (S1) | 1 | 1 | 0 |
Totals counted from the table: 6+9+4+5+1+3+1 = 29 valid rows; killed 6+9+4+5+0+3+1 = 28; survived 1 (U6). Two first-pass mutants (F2, L2) failed to anchor and were rewritten as F2/L2/F8/L4 above; the first pass's 3 collection-error rows are not counted.

## Survivor
- U6 EQUIVALENT: my mutant wrote `from None` on a `raise` that already sits outside the `except` block, so there is no context to suppress.

## Findings
- F-R556-1 LOW: `_bounded` keeps the cut at 300 characters of the escaped text, so a long reason shows `...`; a reader loses the tail. Design.
- F-R556-2 LOW: only `field_agent` and the sentinel CLI are covered; other SDK/CLI call sites that echo a body (I did not scan the repo) may remain; the repository-wide boundary-echo lint (C-505) is the guard for those.

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head rebased on current main.
