# B-COND-PR719-48a050a: LOW condition pushed on PR 719, new head 8ae8dcbda6b4

Added test_the_line_number_counts_physical_lines_including_blank_ones (blank lines before the bad line, expects line 4). Mutants M8 (line number skips blanks) and M7 (zero-based) both killed. test_deployment_agent_journal_shape 30 passed (PYTHONUTF8=1); no source change. Identity Don Hagell both fields. Open: CI, re-review.
Not done (note, not a condition): the reviewer's point that JournalError blocks clear_halt (rotation.py), so a repair is a hand edit; a runbook sentence is a follow-up (B-FU-PR719-runbook-repair).
