# Review PR 747 @ 4318f5b2d470cc7635cf7d0d250ee531a568de96 — federation-broker count and log a failed crossing ledger append (S7-21)
Reviewer: ssl-ff-reviewer-3. ALL RUNS UNVERIFIED (cloud, no GX10).

**VERDICT: PASS WITH CONDITIONS (one MEDIUM, one LOW)** on head 4318f5b2.

## Lineage / identity
- One commit; author and committer Don Hagell <13129187+dhagell@users.noreply.github.com> (HIGH).
- Merge base ebb027a2, main 8 ahead, `git merge-tree --write-tree` clean. Stale base, not the old-lineage defect.
- Diff: api.py +3/-1, engine.py +10/-2, one new test file (5 collected cases). `/health` gains `ledger_append_failures` (additive field).

## Mutants. Baselines unmutated: new file 5 passed; whole federation-broker suite 196 passed.
| # | Mutant | Result |
|---|---|---|
| M1 | no increment | KILLED |
| M2 | increment by 2 | KILLED |
| M3 | count only BLOCK | KILLED |
| M4 | re-raise after counting | KILLED |
| M5 | log `str(exc)` | KILLED |
| M6 | log the scope text | KILLED |
| M7 | log without the exception class | KILLED |
| M8 | log without the decision | KILLED |
| M9 | log at INFO | KILLED |
| M10 | `log.exception` (traceback carries the exception text) | KILLED |
| M11 | no lock around the increment | SURVIVED (full suite 196 passed) |
| M12 | /health drops the field | KILLED |
| M14 | /health off by one | KILLED |
| M15 | narrow `except Exception` to `except RuntimeError` | SURVIVED (full suite 196 passed) |
| M16 | narrow to `except OSError` | KILLED |
| M17 | count before the append | KILLED |
| M20 | counter assigned 1 instead of incremented | KILLED |

Totals counted from the table: 17 valid rows, 15 killed, 2 survivors. 0 equivalent, 0 anchor failures.

## Findings
1. MEDIUM (M15): the only exception the tests raise is RuntimeError. Narrowing the catch to RuntimeError passes the whole suite, yet a real ledger client failure (a connection error or an HTTP error from the client) is not a RuntimeError, so a crossing would 500 instead of keeping its verdict. Parametrise the failing ledger over at least ConnectionError, TimeoutError and ValueError.
2. LOW (M11): the lock is untested; no concurrent-increment test. The count is documented best effort, so a lost update is tolerable; say so or pin it.
3. Observation: the count is in memory and resets on restart (stated in the code comment). `/health` is the only reader; no alert path. Not a defect.
4. The no-echo property (exception text, scope text) is pinned by M5, M6 and M10.
