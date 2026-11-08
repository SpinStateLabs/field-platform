# Review R-FALLBACK-CB2-4d0c331

**VERDICT: PASS WITH CONDITIONS (read-only, post-merge) — batch head 4d0c33153 (range acaf5f24..4d0c3315, MERGE 1 batch cb2)**

Fallback review of the oldest merged batch in STATUS.md (reviewer: fp-reviewer-c). Nothing pushed.

## Checks
- 8 commits, all author AND committer Don Hagell noreply (HIGH). No path under .github/ (HIGH). Files: compliance-crosswalk README (1 line), test_signer_sanitise_c252.py, tools/tests/test_workflow_security_lint.py (HIGH).
- Tests on the head: 235 passed (lint + signer files) (HIGH).
- No secret-shaped strings; canary is an explicit made-up marker (HIGH).

## Mutants on `_DYNAMIC_KEY` (counted from table)
| # | Mutant | Result |
|---|---|---|
| 1 | IGNORECASE dropped | killed |
| 2 | double-quote branch `[^"]*`→`.*` | killed |
| 3 | `\s*` before `[` removed | killed |
| 4 | `\b` dropped | killed |
| 5 | `\s*` inside lookahead removed | killed (2) |
| 6 | single-quote branch `''`→`'[^']*'` | **survived** |

Applied 6, killed 5, survived 1, not applied 0.

## Condition (LOW, non-blocking, MEDIUM confidence)
- Mutant 6: no test distinguishes the empty-single-quote-only literal from any single-quoted literal in the lookahead; a pin such as `github['sha']` as a dynamic case (or an explicit accept case) would fix it. If the survivor is equivalent because another rule catches it, say so in a comment. Put it in a NEW PR.
