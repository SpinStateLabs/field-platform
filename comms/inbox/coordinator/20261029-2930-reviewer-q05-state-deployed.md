# Q-05 reviewer report: STATE.md statements about what is deployed where (main 7b4d6f7; 2,298 lines)

VERDICT: STATE.md is a rolling log, newest section first; its newest dated deploy statement is 2026-10-03. Ten deployed-state lines are dated before 2026-10-05 and nothing in the file after that date confirms or supersedes them; at least two read as current and are not.

OBJECTIONS FIRST
1. A log entry is true at its date; "stale" here means a reader could take it as the present state, not that it was wrong.
2. My keyword filter (deployed, live, serving, armed, build sha next to GB10, Fly or estate) finds statements of this shape only; deploy state described in other words is missed.
3. What is deployed NOW comes from outside this repository (the coordinator's records and my own session notes: GB10 d853ef0 and Fly v13 main-659f31b recorded on 2026-10-25), not from STATE.md; I did not inspect a live estate.

ASSUMPTIONS
1. `STATE.md` at 7b4d6f7, scanned by script for lines with a date before 2026-10-05 and a deployed/live/armed statement about GB10, Fly or the estate. [HIGH]

REASONING
1. Count: 10 such lines: by month 2026-08: 3, 2026-09: 5, 2026-10: 2 (lines 108, 126, 309, 592, 647, 669, 940, 1070, 1806, 1822). Example texts: :108 "GB10 DEPLOYED 2026-10-03 06:54-06:56Z at 38e2142"; :309 "DEPLOYED LIVE 2026-08-30: https://force-field-sandbox.fly.dev"; :592 and :647 the X0 deploys of 2026-09-12; :940 "X4 cross-estate witness BUILT, DEPLOYED and A5 ARMED, 2026-09-13"; :1070 "Phase F code DEPLOYED on the GB10 (switches OFF), 2026-09-14"; :1806 "GB10 DEPLOYMENT - LIVE (2026-08-29, v1.1 code 806d8c0 ...)". [HIGH]
2. Lines that read as current and are not: :126 "ESTATES NOT REDEPLOYED (2026-10-03): GB10 10.0.0.62 unreachable from rog-command" and "Fly still NOT redeployed (flyctl account mismatch)" (:~121-128). Both were superseded by later deploys recorded elsewhere (not in STATE.md). Nothing later in STATE.md says so. [HIGH on the text; MEDIUM on "superseded" (my session record, not a repo file)]
3. The most recent sections (lines 5-93) are dated 2026-10-04 and 2026-10-21 and describe branches (ops-console 0.2.0; ADR-0072, 0071, 0074 DRAFT); they say nothing about the Phase G deploys (flags OFF), the 2026-10-2x estate rollouts, the reviewer-driven fixes (PRs 58-94), or the current GB10 and Fly build SHAs. Lines dated 2026-10-2x that mention deploy/live/GB10/Fly: 1 (a test-run note at :79). [HIGH]
4. Dates in the file after 2026-10-05 are expiries and test runs; the newest date, 2026-12-07 (:384), is a token due date, not an event. [HIGH]
5. There is no "currently deployed" table (estate, build SHA, date, who verified). The facts a reader needs (which SHA runs on the GB10 and on Fly) must be reconstructed from the log. [HIGH]

CONCLUSION
Add a short dated "Deployed now" table at the top of STATE.md (GB10 and Fly: build SHA, deploy date, verification, flags) and strike or annotate :126 and :121-128 as superseded. Not done: confirming each of the 10 lines against live estates or deploy logs.
