# Groomer: C-1163 has two claims, both by lanes the queue lists as stopped

Evidence (names and files only, no values):
- Lane 16 claim: 20261102-0513-builder-lane16-claim-C-1163.md (commit 8988fd4).
- Lane 13 claim: 20261102-0520-builder-lane13-claim-c1163.md (commit 07a2de3). Lane 16's file is earlier by name and by commit order, so Lane 16 is the first claimer (HIGH).
- TASK-QUEUE.md LANE CHANGE 2026-11-02 line says Don stopped builders Lane 12, Lane 13 and Lane 16; builders left are Lane 1, Lane 11, Lane R. Read from the queue, not checked against a Don message (MEDIUM).

Possible state changes, for the coordinator to decide:
1. Name one owner for C-1163 (or release it) so the two stopped lanes do not both write the runbook checklists.
2. If neither lane is running, C-1163 is orphaned and open to Lane 1, Lane 11 or Lane R.

I do not know whether either lane has pushed work; no PR for C-1163 exists in the PR list (read, not measured). TASK-QUEUE.md not edited.
