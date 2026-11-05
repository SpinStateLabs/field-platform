# Review PR 741 @ 04a111ccf47e6b161995b30cd83b7fed2800a327 — spend-governor readers agree with /status (S7-16)
Reviewer: ssl-ff-reviewer-3. ALL RUNS UNVERIFIED (cloud, no GX10).

**VERDICT: PASS WITH CONDITIONS (one LOW)** on head 04a111cc.

## Lineage / identity
- One commit; author and committer Don Hagell <13129187+dhagell@users.noreply.github.com> (HIGH).
- Merge base ebb027a2, main 8 ahead, `git merge-tree --write-tree` clean. Stale base, not the old-lineage defect.
- Diff: api.py +6/-2, core.py +1/-1, usage.py +3/-1, one new test file (6 collected cases).
- Behaviour change to note for Don: `GET /usage/{agent}` for an uncapped agent changes from 200 (period "total") to 404. Intended by the PR; pinned. Callers that relied on the 200 would break (not in source whether any exist).

## Mutants. Baselines unmutated: new file 6 passed; whole spend-governor suite 297 passed.
| # | Mutant | Result |
|---|---|---|
| M1 | revert filter to `if agent_id:` | KILLED |
| M2 | filter on `!= ''` (None filters too) | KILLED |
| M3 | no 404, fall back to "total" | KILLED |
| M4 | 404 becomes 400 | KILLED |
| M5 | 404 text changed (line 564 only) | KILLED |
| M6 | window_seconds = 0 | KILLED |
| M7 | reversed sign | KILLED |
| M9 | `round()` instead of `int()` | SURVIVED (full suite 297 passed) |
| M10 | ignore the cap period (epoch start) | KILLED |
| M13 | 0 when a policy is set | KILLED |
| M15 | 404 also when no usage rows | KILLED |
| M16 | minutes instead of seconds | KILLED |

Totals counted from the table: 12 valid rows, 11 killed, 1 survivor.
Equivalent, not counted: M8 (drop `max(0, ...)`). `start` is the floor of `now` (or the epoch), so `now - start >= 0` for any clock after 1970 (general knowledge, HIGH). The first M5 anchor matched 2 sites (the message appears 8 times in api.py) and was re-run on line 564; the table shows the re-run.

## Findings
1. LOW (M9): the test clock is a fixed whole second, so truncation versus rounding of a fractional "now" is unobserved; with the real clock the value can differ by 1 s. Not claimed anywhere. A test with a clock at xx:30:00.7 would fix it.
2. Observation: `/usage` window_seconds for period "total" is ~1.8e9 s (epoch to now), pinned by `test_total_period_counts_from_the_epoch`. Field description now says so. Fine.
3. Observation: the Field description in usage.py is unpinned (OpenAPI text; documentation only, not counted).
