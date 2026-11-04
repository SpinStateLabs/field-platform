# Correction to the PR 475 verdict (reviewer)

In the report filed for PR 475 head 19d14a49 the line "Totals counted from the table" is wrong and should read: the table has 12 claim rows, 12 OK, 0 failed. The "19 individual checks" figure in that line was not counted from the table and should be ignored. Verdict unchanged: PASS WITH CONDITIONS, CI 7/7 SUCCESS at read, two statements (exit code 2 of the operator-key-file refusal, 403 D.grantor on the GB10 cron mint) not verified.
