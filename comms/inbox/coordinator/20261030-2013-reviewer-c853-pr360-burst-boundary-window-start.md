VERDICT: PASS WITH CONDITIONS on b2bc1290e2f8fdc24ed1275e2b2f1e6f6fa20a0f  (UNVERIFIED: cloud reviewer, no GX10, CI not read)

C-853, PR 360 (spend-governor: pin the token-burst boundary; document the window_start fallthrough) at b2bc129. Two commits; changes are a docstring in core.py (+9) and a new test file (111 lines). This SHA only.

OBJECTIONS FIRST
1. window_start is wrong for a non-UTC aware `now`, and its new docstring does not say it assumes UTC. core.py window_start (daily and monthly branches) formats the calendar fields of `now` as given and labels them +00:00. Probe: 2026-10-31 01:00 at +14:00 (that is 2026-10-30 11:00 UTC) gives a daily start of 2026-10-31T00:00:00+00:00, a UTC instant in the future of the real UTC time; 2026-10-30 23:00 at -05:00 (04:00 UTC on the 31st) gives 2026-10-30T00:00:00+00:00, a window 28 hours long. The service's own clock is UTC (api.py `_system_clock` returns datetime.now(timezone.utc)) so production is correct; the injectable clock (`clock=` in create_app) is documented as "an aware datetime", which admits a non-UTC one. A naive `now` is also formatted as is. Confidence HIGH (observed). The docstring added here describes only the unknown-period fallthrough.
2. The docstring's fallthrough claims check out against the code, with one precision: "GET /caps and POST /usage on such a row raise". Probe: a stored cap row whose period was changed in the database to an unsupported value makes GET /caps, POST /usage, POST /spend, GET /status and GET /totals all answer 500 (not a structured refusal), while the API refuses to create such a row (PUT with period weekly: 422). So the "never reaches this function" claim holds for the HTTP surface, and the way it fails is a bare 500 on five routes, not just two. Whether to meter conservatively or refuse loudly stays open (F-C703-3), as the docstring says. Confidence HIGH.
3. At the function level the fallthrough is as documented: "weekly", "", "Daily" (case), "None" all return the epoch start, so a mis-spelled period counts ALL spend (stricter, never lenient). HIGH.
4. Boundary tests: the burst is inclusive (`>=` at usage.py:122): 4,999 not flagged, 5,000 and 5,001 flagged, in the pure function and through the API; no limit never flags; the detail names count and limit. Window edges: the burst sum includes a row exactly at the window start and excludes one a microsecond earlier; the rolling-throttle read is strict at the edge. These pass (10 in the new file). HIGH.
5. The new test file does not pin window_start's daily and monthly arithmetic; those mutants are killed by older tests in the suite, not by this PR's file. Not a defect; the card's "mutant per boundary" is satisfied by the suite as a whole, not by this file alone. INFO.

ASSUMPTIONS
A1 Card scope: boundary instants and window edges, documented fallthrough versus code at file:line, a mutant per boundary. A2 Production clock is UTC.

REASONING / CHECKS
- Tests: test_burst_boundary_c128.py 10 passed; spend-governor suite 252 passed.
- window_start probe (13 inputs): daily at 23:59:59.999999Z and 00:00:00Z both give that day's midnight; monthly on the 31st, in December and at 00:00 on 1 January give the right first of month; total epoch; unknown strings epoch; non-UTC cases as in objection 1.
- Mutants (each restored, nothing committed): burst `>=` to `>` KILLED; to `>= limit+1` KILLED; to `>= limit-1` KILLED; "no limit" guard replaced by True KILLED (by the new file); daily start +1 second KILLED; monthly start on the 2nd KILLED; total returns today's midnight KILLED (these three by older suite tests, the new file alone passes them). Seven of seven.
- Commits: 2, author and committer Don Hagell no-reply; diff has no address, flag value, credential or deploy status.

CONDITIONS
C1 (non-blocking) State the UTC precondition in the window_start docstring, or convert `now` to UTC inside (a one-line fix with a test at +14:00 and -05:00).
C2 (non-blocking) Decide F-C703-3: a stored unsupported period answers 500 on five routes; a clear 4xx or a startup check would be kinder than a bare 500.

NOT VERIFIED
GX10 full set, CI, other services' window code, behaviour under daylight-saving or leap-second inputs (UTC only here).

CONCLUSION
The boundary tests pin the inclusive burst and both window edges and the mutants die; the fallthrough documentation is accurate for the HTTP surface. The one gap is an unstated UTC assumption in window_start. PASS WITH CONDITIONS, UNVERIFIED.
