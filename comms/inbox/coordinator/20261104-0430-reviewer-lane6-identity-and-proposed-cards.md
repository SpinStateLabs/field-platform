# Reviewer Lane 6: a commit-identity defect on comms, a stray local commit, and proposed new cards

## 1. Commit identity (HIGH CARE for a PUBLIC repo; found while pushing C-644)
My shell had `GIT_AUTHOR_NAME` set in its environment, which overrides `git -c user.name=...`. So the commits Lane 6 pushed to `comms` since 2026-10-28 carry the AUTHOR NAME `donhagell@gmail.com` (a personal address used as a name; the author email was the noreply one). `git log origin/comms --author=donhagell@gmail.com` finds 70 commits. This is the same class as lesson 2 of PR 297 (check author and committer before the first push) and I did not check. From now on I push with `GIT_AUTHOR_NAME`/`GIT_AUTHOR_EMAIL`/`GIT_COMMITTER_*` set explicitly to the repo identity (`Don Hagell <13129187+dhagell@users.noreply.github.com>`) and verify `git log -1 --format='%an <%ae> | %cn <%ce>'` before every push. The 70 existing commits cannot be fixed without rewriting the branch (I will not force-push); Don decides whether to rewrite `comms` (it is a comms branch, not main) or leave it. Other lanes: check `env | grep GIT_` in your shells.

## 2. A stray local commit in the shared checkout
The shared checkout `C:\Users\donal\fpc` (branch `comms`) holds a local commit that is not on origin: `754e120d` "TASK-QUEUE: 5 cloud-reviewer cards C-669..C-673 (PRs 319, 332, 335, 345, 346)" (author name `donhagell@gmail.com`, so not mine; I did not write it), plus a duplicate of my own C-644 commit. It blocks `git pull --rebase` in that checkout (conflict in TASK-QUEUE.md). I did NOT push it. Whoever owns it: rebase it onto origin/comms and push, or drop it. I now push from a separate worktree (`C:\Users\donal\fpc-push-tmp`) so I do not touch that checkout.

## 3. Reports since my last status
C-568 PR 319 delta (PASS on fedacae), C-566 PR 321 (PASS on ddbeb71), C-576 PR 314 delta (PASS on e44a18f), C-644 PR 348 (PASS WITH CONDITIONS on 6b685fd). Taking C-593 (PR 319 delta, head 34895a4) next.

## 4. Proposed new cards (for the coordinator to number)
1. Builder, MEDIUM-LOW (C-644 F-C644-1): finish the 5xx fix in ops-console: bulk rows, fleet-halt rows and the registry-unavailable detail, and the overview, platform and agent-detail section errors still relay an upstream 5xx body (6 of 14 routes probed); apply `_relay` there or reword the commit; marker test per route.
2. Builder, MEDIUM-LOW (C-644 F-C644-2): pin `_seg` on the bulk `agent_ids` and halt `domains` body ids (the only routes where `/` can arrive); three mutants survive today.
3. Builder, LOW (C-644 F-C644-3/-4): keep the HTTP status of a non-JSON upstream answer; add a dotted-id test and read-route `_seg` tests.
4. Builder, LOW (C-576 N1/N2): `style=` attribute context in the innerHTML audit; verify acorn's files, not only the lockfile hash.
5. Don decision: rewrite `comms` to fix the 70 author names, or leave them.
