# Review PR 744 @ c97dd1cfbb73eab30743f9420205d84c2518c308 — agent-registry find_secrets / scan_secrets_text no longer quadratic (S7-14)
Reviewer: ssl-ff-reviewer-3. ALL RUNS UNVERIFIED (cloud, no GX10).

**VERDICT: PASS WITH CONDITIONS (one MEDIUM)** on head c97dd1cf.

## Lineage / identity
- One commit; author and committer Don Hagell <13129187+dhagell@users.noreply.github.com> (HIGH).
- Merge base ebb027a2, main 8 ahead, `git merge-tree --write-tree` clean. Stale base, not the old-lineage defect.
- Diff: discover.py +7/-5, redaction.py +13/-3, one new test file (4 tests). The test copies the old algorithms as an oracle and compares byte-for-byte on 200 random strings plus a fragment corpus, in both bounded and loose modes with and without the very-broad pattern.

## Mutants. Baselines unmutated: new file 4 passed (0.5 s); whole agent-registry suite 315 passed.
| # | Mutant | Result |
|---|---|---|
| M1 | `bisect_right` for the candidate end bound | KILLED |
| M2 | `>=` (touching spans count as overlapping) | KILLED |
| M3 | drop the `i and` guard | KILLED |
| M4 | append instead of sorted insert | KILLED |
| M6 | `ends` inserted at the wrong index | KILLED |
| M7 | no overlap check | KILLED |
| M8 | bisect on `start` instead of `end` | KILLED |
| Q1 | revert find_secrets to a flat quadratic scan | KILLED (by the 10 s bound: 31.8 s) |
| Q2 | revert scan_secrets_text to count newlines from 0 | SURVIVED (4 passed in 5.3 s; full suite 315 passed) |
| L1 | line counter starts at 0 | KILLED |
| L2 | newline count skips the first character | KILLED |
| L3 | `at` never advances | KILLED (by line-number comparison) |

Totals counted from the table: 12 valid rows, 11 killed, 1 survivor.
Equivalent, not counted: L4 (`at = hit.end`). A matched value contains no newline, so the skipped span adds nothing; run result 4 passed, full suite 315 passed.

## Findings
1. MEDIUM (Q2): the claimed scale fix for `scan_secrets_text` is not pinned. Reverting it to `text.count("\n", 0, hit.start)` per hit makes the 40,000-hit test take 5.3 s here, under the 10 s bound, so it passes. The `find_secrets` half is pinned (Q1: 31.8 s). The docstring says the old `scan_secrets_text` took 31.3 s at 20,000 hits on the author's machine; on this box 40,000 hits took 5.3 s, so the bound is 2x the measured regression, not a margin. A bound under about 3 s would pin it but would flake on slow CI. Better: assert on work, for example count `str.count` calls via a spy, or compare two sizes' ratio.
2. Correctness otherwise holds: the new `find_secrets` equals the oracle on the whole corpus and the line numbers equal the old per-hit count.
