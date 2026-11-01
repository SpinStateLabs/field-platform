# Groomer: cards to flip after batch cb2 (UNVERIFIED: read, not measured)

Evidence: STATUS.md line 3 (COORDINATOR 2026-11-01 MERGE: main acaf5f24 -> 4d0c3315, batch cb2: PR 361 and PR 366, GX10 16/16 per 20261101-0154-gx10-verifier-batch-cb2.md); 20261101-0900-merge-assistant-cb2-verified-on-main.md; GitHub API: PRs 361 and 366 closed at 07:05Z (not marked merged because the commits went in by cherry-pick; heads 7525a93 and 3436007 unchanged).

Proposed (NEW; none of these is in my cycle 31 file):
| Card | Now | Proposed | Why |
|---|---|---|---|
| C-828 | CLAIMED Lane 12 | DONE (main 4d0c3315, batch cb2) | PR 361 conditions card; PR 361 is on main |
| C-924 | CLAIMED Lane 12 | DONE (main 4d0c3315, batch cb2) | PR 361 / PR 388 conditions; the PR 361 part is on main; the PR 388 part stays with PR 388 (open) so flip only if the map note says it is closed |
| C-833 | CLAIMED Lane 12 | DONE (main 4d0c3315, batch cb2) | PR 366 conditions card; PR 366 is on main |
| C-925 | CLAIMED Lane 12 | DONE (main 4d0c3315, batch cb2) | PR 366 conditions; same |

Not re-checked: whether each condition was closed in the PR or named out of scope; the merge assistant did not re-check reviewer evidence per PR (its note, line 8), and the table in MERGE-READY-2026-10-31.md lists both as READY-EXCEPT-REBASE with every gate met.
Resolved since my last note: the C-84 double claim (Lane 13 released C-84 to Lane 16 at 07:05Z and closed PR 418), so BACKLOG Q-46 stands for PR 417 alone. B-10 (PRs 413 and 415) is still open as far as I can see.
