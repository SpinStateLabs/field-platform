# B-COND-PR738-ca4bd36 done (ssl-fp-architect, builder role): PR 738 new head 785a5bb80

Pushed one tests-only commit to `fix/roster-csv-error-s7-11`; no production file changed. Author and committer Don Hagell. New file `services/lifecycle-manager/tests/test_pr738_condition_pins.py` (11 tests). The PR needs a re-review on the new head (reviewer-6 report 20261105-1000, conditions V1, V6, V9, V11, V12, V13, V20).

## Mutants (mine, one at a time on api.py, file restored after each; tree clean)
| mutant | result |
|---|---|
| V1 floor 59 | KILLED |
| V6 `isascii` dropped | KILLED (Arabic-Indic and fullwidth digits) |
| V9 floor warning removed | KILLED |
| V11 cap removed | KILLED (300k-short-row class, exactly 1 MiB passes, 1 MiB + 1 is 422) |
| V12 cap + 1 | KILLED |
| V13 cap - 1 | KILLED |
| V20 empty-roster check removed | KILLED |
7 of 7 killed (counted from the table).

## Runs (HIGH, Windows, Python 3.14)
- New file 11 passed; with the PR's own roster files (test_roster_csv_error, test_api_env_and_roster_errors, test_roster_aliases) 59 passed.
- Whole lifecycle-manager suite NOT run here (my PYTHONPATH lacks conformance_sentinel for test_provision_wrapper). CI and GX10 on the exact head still required.

## Note
An owner-less roster in the body answers 503 (`RosterUnavailable`), not 422; the test pins what the code does. Not covered (reviewer LOW): V21/V26 redundant DictReader wrapper, V30 stderr vs stdout. The interval floor 60 is still "Don to confirm" per the code comment.
