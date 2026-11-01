# BUILDER Lane 12: gates reset by my two pushes (per the head-freeze note 20261101-0731)

Both pushes were condition fixes on PASS WITH CONDITIONS heads, carded by the coordinator (C-835, C-1025): the note's exception. For the record, what each push resets:

- PR 368 `claude/vibrant-mendel-vjdfue`, 1f7f61f -> 1fac649 (C-835, report 20261101-0810): resets the C-775 and C-790 verdicts (PASS WITH CONDITIONS on 1f7f61f), GitHub CI 7 of 7 on 1f7f61f (not yet read on 1fac649), and Lane 16's GX10 set on 1f7f61f. Needed again: reviewer delta on 1fac649, CI read, GX10 run. PR 380 still carries 1f7f61f, not these commits.
- PR 316 `fix/console-csp-headers-c456`, 6ae698f -> 3c769c7 (C-1025, report 20261101-0905): resets the C-567 verdict (PASS WITH ONE NON-BLOCKING FINDING on 6ae698f, with its CI-equivalent run) and the C-458 verdict (PASS WITH CONDITIONS on 6ae698f). Needed again: reviewer delta on 3c769c7 (one commit, two Caddyfiles and two test files), CI read, GX10 run.

Nothing else was pushed by this lane to any PR branch. The PR texts carry the same sentence. Lane 12 stays idle on the 5-minute poll.
