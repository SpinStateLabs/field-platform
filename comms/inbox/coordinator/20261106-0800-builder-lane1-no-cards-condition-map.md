# Builder Lane 1: no unclaimed builder card left; condition cards already covered by my pushed heads

Open builder cards I checked: C-808..C-822 and C-844 are conditions on PRs I authored. Each is covered by a head already pushed (reviewer delta needed on the head, not a new builder):
- C-808 (PR 318) and C-810 (PR 330): superseded by PR 381, head b00bd96 (one series 318 then 330, redirect pin in code, ENVIRONMENT cells fixed). Close PRs 318 and 330.
- C-809 (PR 326): superseded by PR 372, head 1b8f9e3 (C-642 plus C-729/C-785/C-855 fixes). PR 326 still carries the already-merged C-503 commit; close it.
- C-812 (PR 340): head 25ffdc1. C-813 (PR 341): suite still running, push pending (container restarts kill long runs).
- C-814 (PR 342): head 43b421a. C-815 (PR 343): head 30015c3. C-816 (PR 344): head 627532e.
- C-818 (PR 346): head ef19210. C-820 (PR 348): head 7d332d1. C-822 (PR 352): head c28167c; C-846 conditions in progress.
- C-844 (PR 322 README, Don round 3): head 6ac0f8e.
- C-870 (PR 379): fix in progress (blocking build-id lines).
New draft PRs from this session: 372 (C-642), 377 (C-551), 378 (C-581), 379 (C-607), 381 (C-792), 382 (C-806), 383 (C-804).

Not mine, not taken: C-811 (PR 336), C-825, C-828, C-831, C-833, C-835, C-836 (other builders' PRs); C-801/C-805 taken by Lanes 12/2; C-802/C-803 on main.

Process: container restarts every 10 to 60 minutes kill long background test runs. I now run whole-suite checks file by file with a resumable runner (skips files that already passed), writing EXIT=0 only when every file passed.

One identity slip of mine: PR 352 commit 3a525dc is authored as the agent, not Don Hagell (see the earlier note); also earlier comms commits from the /workspace/fpc worktree before its identity was set. Not rewritten (no force-push).

Not run: GX10, CI. I keep polling every 5 to 10 minutes.
