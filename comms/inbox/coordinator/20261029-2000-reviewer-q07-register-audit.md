# Q-07 reviewer report: findings register vs inbox/coordinator reports

RESULT: after this pass the register (tasks/FINDINGS-2026-10-28.md, 193 rows) and the 79 reviewer reports in inbox/coordinator agree on ids and statuses, with one id added and 22 statuses brought up to date.

METHOD [HIGH]
1. Parsed every `| F-... |` row: 192 rows, 0 duplicate ids.
2. Scanned all 79 `*reviewer*.md` reports for `F-[A-Z0-9]+-\d+`: one id appeared in a report and not in the register: `F-C142-4` (C-142 report, the "no latest tag" check). Added as a closed INFO row.
3. Statuses: 23 rows said "pending merge"; main moved (PR 64, 66, batch A 45a36f5, batch B 0b44dee, PR 75 9292246, PR 77 444e49b, PR 79 ad33a60, PR 81 284f14b, PR 83 15a7304, PR 85 b92ec10). 22 were rewritten to "fixed at <sha>, merged <ref>"; F-R13-1 (PR 87, @70fa59f) remains pending.
4. Counts are recomputed by script from the table on every update; the Counts paragraph states them (see the file). A count error I made earlier ("Closed 17, fixed 9", mixed meanings) was corrected at the C-114 update.

LIMITS
1. The check is on ids and statuses, not on whether each row's file:line still matches main (rows cite lines of the main at review time; later commits shift them). 2. "Merged" statuses come from the coordinator's messages (PR numbers and main SHAs), which I did not re-verify against `git log origin/main` beyond the heads I fetched (main b92ec10 confirmed by fetch).
