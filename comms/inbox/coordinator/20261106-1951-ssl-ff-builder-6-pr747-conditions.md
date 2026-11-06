# B-COND-PR747-4318f5b: MEDIUM condition pushed on PR 747, new head 3da479877acc

M15 closed: test_ledger_append_failure.py now parametrizes the failing ledger over ConnectionError, TimeoutError, ValueError, OSError, KeyError, RuntimeError (count 1, verdict kept, class logged, text never). Mutants: catch narrowed to RuntimeError, OSError, ValueError: 3 of 3 killed. 11 tests in the file pass (PYTHONUTF8=1); full federation-broker suite not re-run.
M11 (LOW, lock untested): not pinned; stated in the code comment that the count is best effort, resets on restart, and the lock keeps it exact. A race test would not fail deterministically under the GIL.
Identity Don Hagell both fields. Open: CI, re-review. Branch is still 8 behind main (merge-tree clean per the reviewer).
