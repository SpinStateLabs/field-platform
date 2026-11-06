# B-COND-PR741-04a111c: LOW condition pushed on PR 741, new head 3c532236857a

Added test_window_seconds_truncates_a_fractional_clock_it_does_not_round (clock 12:30:00.7 and 12:30:00.999, daily window must read 45000). Mutant M9 (round instead of int) is killed; no source change. test_reader_consistency 7 passed (PYTHONUTF8=1, 187 s on this loaded machine). Identity Don Hagell both fields. Open: CI, re-review.
For Don (from the reviewer, not mine to decide): GET /usage/{agent} for an uncapped agent changes from 200 to 404; no caller was checked.
