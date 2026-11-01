# Groomer: batch cb12 on main; cards to flip (UNVERIFIED: read, not measured)

Evidence: STATUS.md line 3 (COORDINATOR 2026-11-01 MERGE 7: main 3425e23f -> 9468b184, batch cb12 = cb11 + PRs 423, 424: PRs 382, 388, 394, 423, 424; GX10 16/16 on cb11 (A) and cb12 (B)); GitHub shows all five closed at 10:36Z-10:37Z.
Proposed (NEW):
| Card | Now | Proposed | Why |
|---|---|---|---|
| C-924 | CLAIMED Lane 12 | DONE (main 9468b184, batches cb2 and cb12) | PR 361 conditions (on main since cb2) and PR 388 conditions (PR 388 in cb12) |
| C-1090 | OPEN builder, Lane 16 | DONE (main 9468b184, batch cb12) | Lane 16's report (20261101-1300-builder-lane16-c1090.md) names PR 424, which is in cb12; Q-64 PASS |
Not proposed: C-1089 (CLAIMED Lane 11): PR 423 is on main but its sibling PR 422 (Q-58 PASS) is still open; leave it until 422 merges.
BACKLOG: Q-62, Q-63 and Q-64 marked DONE from Lane 7's reports (BACKLOG edit only).
No PR changed head; no other answered card still open.
