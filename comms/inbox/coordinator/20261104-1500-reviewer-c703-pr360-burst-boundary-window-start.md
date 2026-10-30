VERDICT: PASS WITH CONDITIONS on 3aacd5a3e36fca9dc7904bcb226be1ca902848b1 (UNVERIFIED: cloud reviewer, no GX10, CI not read; the PR's new test file ran: 7 passed; the rest of the spend-governor suite was NOT run)

Head matches the card. One commit on main; author and committer are the no-reply identity. Files: services/spend-governor/src/spend_governor/core.py (+8: a docstring only), tests/test_burst_boundary_c128.py (+76, new). The code change is documentation only.

OBJECTIONS FIRST
1. The new docstring on window_start says an unknown period "counts from the epoch, as total", "a refusal at the door and a conservative count behind it", reachable from "a store row written outside the model". PROVEN not to be what happens: with a cap row whose period was set to an unknown word directly in the database, reading the cap raises a validation error (SpendCapConfig pins the period), so GET /caps/<agent> and POST /usage for that agent fail with an unhandled validation error (a 500 in a server; the test client re-raises it). The "conservative count" is only reached by calling window_start with a bare string, never through a stored row. So the claim "fails toward counting more spend" holds for the function but not for the path the comment cites; the real behaviour on such a row is that usage events for the agent are not recorded at all. MEDIUM-LOW (documentation above what the code enforces; plus a metering stop on a hand-edited row).
2. The burst boundary is pinned, but the WINDOW edges are not: in this PR's file, changing the window query from "at or after the start" to "after the start" and moving the window start by one second both leave all 7 tests green. The card asks for window edges. A probe shows the oldest edge is inclusive (a row at exactly the window age counts); no test in this PR says so. LOW-MEDIUM. (Other files in the suite may pin it; I did not run them.)
3. The burst test is the API-level sum 2000 + 3000 = 5000 against limit 5000: correct, but it only varies the limit side, not a second event landing exactly on the window edge. Same gap as objection 2.
4. A since value spelled with a trailing "Z" matches nothing (text comparison of the stored "+00:00" spelling): window_tokens(since in Z form) returned 0 in my probe. The API always builds the start with isoformat(), so no live path is affected; a future caller could be. LOW.
5. Two windows with different edges coexist (burst count inclusive, throttle strict); documented in core.py:575-576. The PR does not touch that.

ASSUMPTIONS
A1 "Burst boundary" = the comparison in usage.py:121-122 (count of tokens in the window at or above the limit is rogue). A2 Probes used the real store and API in-process with temp files; rows inserted by SQL only to set timestamps. A3 One interpreter.

REASONING
1. Boundary at limit-1, limit, limit+1: pure function, flagged False/True/True (test lines 28-33); API path: 4999 not flagged; exactly 5000 flagged. Mutants: ">=" to ">" -> 3 failed; ">=" to ">= limit-1" -> 2 failed. The boundary is pinned in both directions. HIGH.
2. Detail text carries the count and the limit: tested; a message mutant was not run (the arithmetic and the text read the same variables). MEDIUM.
3. No limit never flags (None policy, None limit): tested. HIGH.
4. Window edge mutants (rolling start replaced by "now": 1 failed; edge ">=" to ">": 7 passed; start shifted by one second: 7 passed). So the rolling start is pinned, its exact edge is not. HIGH.
5. window_start itself: a function call with "weekly", "" and "DAILY" returns the epoch string; so a case variant of a valid period counts from the epoch (conservative). The existing test_cap_windows_c124.py:61 pins "weekly equals total" (read, not run). HIGH.
6. Stored-row probe: after setting a cap row's period to "weekly" by SQL: GET /caps/a raised a validation error; POST /usage raised the same error; other routes unaffected. The docstring's "counts from the epoch" is therefore unreachable through the store. HIGH.
7. Diff scan: no address, SHA, flag value, deploy status or credential. HIGH.

CONCLUSION
PASS WITH CONDITIONS. The burst boundary is now pinned and the mutants confirm it. The documentation added for window_start claims a behaviour the stored-row path does not have, and window edges remain unpinned in this PR. Conditions, none blocking:
- C1 F-C703-1: reword the docstring ("from the function's own point of view; a stored row with an unknown period fails validation on read") or make the read path tolerate such a row as the docstring says; decide which behaviour is wanted (a metering stop versus a conservative count).
- C2 F-C703-2: add a test for a row exactly at the window age and one a microsecond older.
- C3 F-C703-3: decide whether usage events for an agent with a bad cap row should be refused loudly (current: unhandled error) instead.

FINDINGS
F-C703-1 MEDIUM-LOW, services/spend-governor/src/spend_governor/core.py:396-403 (window_start docstring) versus the read path that builds SpendCapConfig from a row; PROVEN (GET /caps and POST /usage fail on a row with an unknown period).
F-C703-2 LOW-MEDIUM, services/spend-governor/tests/test_burst_boundary_c128.py (no window-edge test; edge and one-second mutants survive in this file). PROVEN.
F-C703-3 LOW, services/spend-governor/src/spend_governor/core.py:779-786 (window_tokens compares text; a Z-spelled start matches nothing). PROVEN.
F-C703-4 INFO, core.py:575-576 two windows with different edge rules. HIGH.

NOT VERIFIED: the rest of the spend-governor suite (whether another file pins the window edges); CI; what the server returns for the unhandled validation error (500 assumed); GX10 run.
