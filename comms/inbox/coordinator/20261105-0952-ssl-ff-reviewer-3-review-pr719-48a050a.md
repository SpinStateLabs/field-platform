# Review PR 719 @ 48a050a8c11cd305af518d0e1c47b7088146c76a — deployment_agent journal: unreadable transition state fails closed (S6-19)
Reviewer: ssl-ff-reviewer-3. ALL RUNS UNVERIFIED (cloud, no GX10).

**VERDICT: PASS WITH CONDITIONS (one LOW, one note)** on head 48a050a8.

## Lineage / identity
- One commit; author and committer Don Hagell <13129187+dhagell@users.noreply.github.com> (HIGH).
- Merge base ebb027a2, main 8 ahead, `git merge-tree --write-tree` clean. Stale base, not the old-lineage defect.
- Diff: journal.py +11/-1, one new test file (29 collected cases).

## Mutants (journal.py), new test file unmutated: 29 passed
| # | Mutant | Result |
|---|---|---|
| M1 | drop the check | KILLED |
| M3 | drop isinstance(str) (list/dict states) | KILLED |
| M4 | any str is readable | KILLED |
| M5 | case-insensitive state | KILLED |
| M6 | empty string readable | KILLED |
| M7 | line_no zero-based | KILLED |
| M8 | line_no skips blank lines | SURVIVED |
| M9 | invert the event test | KILLED |
| M10 | event startswith "transition" | KILLED |
| M11 | message echoes the state value | KILLED |
| M12 | message echoes the line | KILLED |
| M13 | null state readable | KILLED |
| M14 | check only when "state" key present | KILLED |
| M15 | check every event, not just transitions | KILLED |
| M16 | raise ValueError not JournalError | KILLED |

Totals counted from the table: 15 valid rows, 14 killed, 1 survivor. 0 equivalent, 0 anchor failures (M2 was dropped from the script before running; not counted).
Survivor M8 against the whole `tools/tests` suite with sibling service paths on PYTHONPATH: baseline 1 failed / 3836 passed / 6 skipped; M8 identical 1 failed / 3836 passed. The 1 baseline failure is pre-existing and was not counted as a kill; I did not identify it. M8 survives the whole suite.

## Findings
1. LOW (M8): the error text "journal line N" counts physical lines including blanks (correct, `enumerate` over the raw split). No test has a blank line before the bad line, so a line number that skips blanks is unpinned. A human repairing the file would be sent to the wrong line. Add one case with a blank line before the bad one.
2. Note: `JournalError` from `entries()` is not caught by any caller in tools/ (grep: only journal.py references it). `rotation.py:271` (`clear_halt`) and `rotation.py:378/382` call `entries()` unguarded, so a damaged line also blocks `clear_halt`, the one path a human uses to recover a halted journal. The message says "a human must repair the journal", so the fail-closed intent holds, but a repair must be a hand edit. Not a defect; worth stating in the runbook.
