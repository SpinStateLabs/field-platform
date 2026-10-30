VERDICT: PASS WITH CONDITIONS on main 5808a5cd6186566a2233105beaf3913b1ae11e51

C-526 spend-governor standing re-audit (Lane 7). Scope: services/spend-governor api.py/core.py; the status, spend, totals and usage endpoints conformance-sentinel calls (engine.py:86-126, :438); the governor side of the fail-closed contract.

OBJECTIONS FIRST
1. The sentinel treats any non-200/201 as ConnectionError and blocks, so a governor 500 looks "safe"; that hides governor bugs rather than proving the governor is right.
2. Bounds on request models are easy to remove without a test noticing.
3. "Exact action string" limits mean a spelling variant is metered but never throttled.

ASSUMPTIONS
A1 Tree = main 5808a5c, clean. A2 Real app via TestClient, temp DB, made-up ids, no ledger. A3 Sandbox timezone is UTC (matters for finding 4).

REASONING / RESULTS
1. Suite: spend-governor 242 passed [HIGH]. 15 hand mutants, 13 killed, 2 survivors (below). Killed: negative cents, negative actions, /spend uncapped open, /usage uncapped open, /totals uncapped open, sentinel row without action, shadowed on a non-sentinel row, per-action match loosened, throttle applied while BLOCK, ledger-drop counter removed, sentinel row re-ledgered, MAX_AMOUNT removed, rate-period case/whitespace folded.
2. Uncapped agent is refused (404) on /status, /spend, /usage, /totals; a made-up id probe confirmed all four [HIGH]. This is the contract the sentinel relies on (engine.py:106-126, :444-448).
3. F-C526-1, /totals 500 on an out-of-range instant [HIGH, probe; severity LOW]: since="0001-01-01T00:00:00+05:00" and "9999-12-31T23:59:59-23:59" parse (api.py:419) then `.astimezone(utc)` (api.py:424) raises OverflowError, uncaught: 500 "Internal Server Error". Valid forms (date-only, Z, offsets) 200; garbage 422. Effect: the sentinel blocks (engine.py:438-443), so fail closed; the since value comes from the token's own issued_at. Same class as the MAX_AMOUNT overflow fix (core.py:143). Fix: catch OverflowError with ValueError and return 422; add the two strings to a test.
4. F-C526-2, survivor "negative tokens accepted" [HIGH, mutant]: `tokens` ge=0 on SpendRequest (api.py:70) has no test; remove it and 242 stay green. With it removed a caller could post negative tokens and lower the window total (a refund). Cents and actions bounds ARE tested. Severity LOW-MEDIUM (guard exists, unpinned). Fix: one parametrized test over cents/tokens/actions with -1. UsageRequest bounds (api.py:95-97) not mutated by me.
5. F-C526-3, survivor "naive since read as local time" [MEDIUM]: replacing replace(tzinfo=utc) by tzinfo=None (api.py:422) survives because the sandbox runs in UTC; on a host with another TZ the naive instant would shift. Fix: a test that sets TZ (time.tzset) and asserts the UTC reading.
6. F-C526-4, action spelling [HIGH, probe]: with a limit of 2 per 1h on "tool_call", three rows each under "Tool_Call", "tool_call " (trailing space), "tool_call​" and "tool-call" give OK and no throttle; two exact rows give THROTTLED. By design ("verbatim", core.py:120-126 style) and the sentinel passes the action it checked, so it affects self-reporting agents only; /status without ?action ignores per-action limits (api.py:404-407). Severity LOW; decision for Don: reject or normalise unknown action spellings, or leave exact.
7. Big values [HIGH, probe]: three /spend rows at MAX_AMOUNT (10**12) plus two /usage rows at 10**12 tokens: no 500, state BLOCK, /totals 200 (spent_cents 3004820000000). The C-246 bound holds for row counts tested; ~9.2M rows to the signed-64-bit limit not tested.
8. Ledger outage path logs a warning and counts ledger_appends_dropped (api.py:165-175), unlike kill-switch (C-525 F-C525-3).

CONCLUSION: fail-closed refusals on an uncapped agent are solid and well killed; one 500 on extreme instants, two unpinned guards. PASS WITH CONDITIONS: F-C526-1 and the two tests (F-C526-2/-3); F-C526-4 is a decision.

What I did NOT do: no wire/auth run; no ledger-connected run; no rate-limit window arithmetic mutants (window_retry_after); no price-book/usage normalisation audit (normalize_model); no escalation resolve path; no GX10; no whole tools suite.
