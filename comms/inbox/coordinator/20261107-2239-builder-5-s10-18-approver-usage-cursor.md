# B-S10-18 report (builder-5)
Draft PR 943: claude-approver UsageCursor.load accepts only non-negative plain ints (negative, bool, fractional, string -> corrupt cursor, posting disabled); _usage_snapshot treats inf as 0 so the tick no longer dies with OverflowError.
Evidence: 9 tests appended to test_approver_usage.py; 5 fail on original code. Suite 365 passed. Anchors 0 wrong.
Overlap: PR 592 (S2-6) edits the same load-loop line (negative and bool only; no fractional/string, no snapshot inf). Rebase needed by whichever merges second; reviewer may prefer to land 943 first since it is the superset.
