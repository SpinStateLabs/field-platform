# Q-74 read of PR 426, head f7d8b71e9858b3faeab1772acfbd25da36f73aec (git ls-remote and gh api agree)

Reader: grooming assistant. Not the author. Read, not measured: nothing was run and no commit id was checked against `git log` of main (my clone of main is shallow).

Checked against comms/STATUS.md (HIGH, direct read):
1. The eight range lines chain with no gap: acaf5f24 > 4d0c3315 > 7de2a064 > 6a37ae76 > b152e955 > 198c4df2 > 3425e23f > 9468b184 > 9addf44f. Each end/start matches STATUS MERGE 2..8; MERGE 1 start/end not re-read.
2. Commit counts 8+2+18+21+6+11+21+3 = 90, equal to the header's 90. The per-merge counts for merges 3..8 match STATUS lines; 2 and 1 not matched.
3. PR lists for merges 3, 4, 5, 6, 7, 8 match the STATUS batch lines (317/331/332/333/337/338; 349/363/373/375; 322; 356; 382/388/394/423/424; 401/403/404). Merge 2 (412, 413) matches the STATUS line start. Merge 1 (361, 366): not checked.

Not checked (I do not know): each commit id's existence on main and each prose clause against its commit; that is a job for a reader with the full main history.
Result: no inconsistency found in what I could read. This is not a PASS on the whole diff.
