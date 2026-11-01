# BUILDER Lane 1: C-1066 covered by Lane 12's own commits; claim withdrawn

Correction to my 20261101-0700 note: Lane 1 does not take C-1066. Read through git (heads and --stat only; no tests, mutants or GX10 run by Lane 1):
- PR 369 head is now 40951fe (was 6f1fd7d): Lane 12's test-only commit covers F-C1057-369-1 and -2 (per Lane 12's note 20261101-1200-builder-lane12-c1066-c1073.md).
- PR 394 head is now e57d1ad (was cf335e6): Lane 12's two commits cover F-394-1 (allow-list of fixed-message kinds) and F-394-3 (recursion guard pin).
- PR 331 is unchanged at 543fe63; the optional F-C1056-331-1 changes CLI behaviour (the exit code for `--min-anchors 0`) and stays with the author or a decision by Don or the coordinator.
- C-1073 (PR 359): Lane 12 also dropped its duplicate of Lane 1's d3e807e. Please mark C-1066 and C-1073 covered.
