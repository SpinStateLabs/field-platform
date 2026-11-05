# Review PR 716 @ 8697ab0c084dcb0a3ed9f1b86d2e6bc681274f62 — conformance-sentinel escalation-trigger edges + SPEC (S6-14)
Reviewer: ssl-ff-reviewer-3. ALL RUNS UNVERIFIED (cloud, no GX10).

**VERDICT: PASS WITH CONDITIONS (one MEDIUM)** on head 8697ab0c.

## Lineage / identity
- One commit; author and committer Don Hagell <13129187+dhagell@users.noreply.github.com> (HIGH).
- Not a descendant of current origin/main: merge base ebb027a2, `git merge-tree --write-tree` clean. Stale base, not the old-lineage defect.
- Diff: SPEC.md +6, one new test file (5 collected cases). No source change; engine.py:585-592 unchanged.

## Mutants (engine.py step 7), baseline whole suite 268 passed
| # | Mutant | Result |
|---|---|---|
| M1 | skip blank/space triggers | KILLED |
| M2 | forward leg only (`t in a`) | KILLED |
| M3 | reverse leg only (`a in t`) | KILLED |
| M4 | `.strip()` the trigger | KILLED |
| M5 | trigger not lowercased | SURVIVED (full suite 268 passed) |
| M6 | `and` instead of `or` | KILLED |
| M7 | skip only the empty trigger | KILLED |
| M8 | action not lowercased | SURVIVED (full suite 268 passed) |
| M9 | skip empty and whitespace-only triggers | KILLED |

Totals counted from the table: 9 valid rows, 7 killed, 2 survivors. 0 equivalent, 0 anchor failures.

## Survivors M5, M8 — MEDIUM
The PR adds to SPEC.md: "match as a case-insensitive substring in BOTH directions". No test in the whole suite pins the case-insensitivity: every trigger and action in the new file is lowercase. A change to a case-sensitive match passes 268 tests. Condition: add one test with an upper-case trigger against a lower-case action and the reverse (kills both).

## Other
- The SPEC statement "only the empty string and a single space match every multi-word action" is pinned (M1, M4, M7, M9 killed; the 3-space test). Accurate.
- The fail-closed rationale is a design claim, not behaviour; no objection.
