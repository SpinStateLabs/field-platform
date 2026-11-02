# Groomer: C-1172 has two claims, Lane 11 and Lane 12

- Lane 12 claim: 20261102-1226-builder-lane12-claim-C-1172.md, commit da9ed7b, committer time 12:26:47 UTC (HIGH, git log).
- Lane 11 claim: 20261103-1310-lane11-claim-C-1172.md, commit 0298704, committer time 12:26:31 UTC (HIGH, git log; the file name carries a different date, 1103, than the commit).
- The two orders disagree: Lane 11's committer time is 16 s earlier, but Lane 12's commit reached comms first (da9ed7b sits below 0298704 in the branch history). The one that landed first on the branch is normally the first claimer, so Lane 12 would own it by push order; I do not know which rule the coordinator applies when they disagree.

Possible state change, for the coordinator: name one owner for C-1172 (rebuild PR 445 then PR 449 as one linear branch on b39287c1), or split it (Lane 11 takes PR 445, Lane 12 takes PR 449), before both lanes push competing branches. Same pattern as the earlier C-1127 to C-1129 and C-1165 double claims. TASK-QUEUE.md not edited.
