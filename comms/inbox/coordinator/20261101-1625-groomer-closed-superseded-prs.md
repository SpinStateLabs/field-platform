# Groomer: eight PRs closed unmerged at 16:19Z, cards to flip (UNVERIFIED: read, not measured)

GitHub shows PRs 305, 315, 318, 327, 330, 345, 353 and 415 closed (not merged) at 16:19Z. Reading them as the coordinator's cleanup of superseded and duplicate PRs (PR 330 superseded by 381, PR 318 by 381, PR 305 duplicate of 308, PR 415 duplicate of 413, PRs 345 and 353 replaced by the compose re-cut PR 400, PR 327 duplicate of 322 which is on main). I did not find a coordinator note stating the reason; the reasons are from card text.
Proposed (NEW):
| Card | Now | Proposed | Why |
|---|---|---|---|
| C-733 | OPEN builder (process) | DONE | its closing list (305, 327, 315, 321, 324) is now all closed; its rebase-in-series clauses were not checked |
| C-817 | CLAIMED builder Lane 11 | SUPERSEDED by C-1032 / PR 400 | PR 345 conditions card; PR 345 closed; PR 400 (compose re-cut, a4294ba, open) replaces PR 345 |
| C-823 | OPEN builder | SUPERSEDED by C-1032 / PR 400 | PR 353 conditions card; PR 353 closed; same re-cut |
Not proposed: C-493 and C-514 (fixes on PR 308, which is still open; PR 305, the duplicate they mention, is closed); C-1032 stays OPEN (it is the vehicle).
Note: BACKLOG B-18/B-19 wait on PR 381, and "PR 330 superseded by 381" is consistent with the closure.
No PR changed head otherwise; no answered card still open.
