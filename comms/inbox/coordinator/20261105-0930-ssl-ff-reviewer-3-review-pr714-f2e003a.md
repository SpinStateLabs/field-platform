# Review PR 714 @ f2e003a9d53912960866e284c89b710ce2848a65 — attestation-reporter `_sweep_rows` wrong-typed token_id (S6-12)
Reviewer: ssl-ff-reviewer-3. ALL RUNS UNVERIFIED (cloud, no GX10).

**VERDICT: PASS WITH CONDITIONS (one LOW)** on head f2e003a9.

## Lineage / identity
- One commit. Author and committer both Don Hagell <13129187+dhagell@users.noreply.github.com> (HIGH).
- Not a descendant of current origin/main: merge base ebb027a2, main is 8 commits ahead. `git merge-tree --write-tree` is clean. This is a stale base, not the old-lineage defect; rebase is optional.
- Diff: engine.py +4/-2, one new test file (4 tests, 7 params with the parametrize).

## Behaviour pinned and mutants
Baseline (unmutated, whole attestation-reporter suite): 262 passed. No baseline failure counted.

| # | Mutant | Result |
|---|---|---|
| M2 | drop the `isinstance(k, str)` filter | KILLED |
| M3 | accept int keys | KILLED |
| M4 | non-str becomes "" instead of None | KILLED |
| M5 | accept list keys | KILLED |
| M6 | accept bool keys | KILLED |
| M7 | accept dict keys | KILLED |
| M8 | invert the isinstance test | KILLED |
| M9 | payload guard checks list instead of dict | KILLED |
| M1 | revert payload guard to `(payload or {})` | SURVIVED (full suite 262 passed) |

Totals counted from the table: 9 valid rows, 8 killed, 1 survivor. 0 equivalent, 0 anchor failures.

## Survivor M1
`field_core.ledger.Event.payload` is `dict[str, Any]` (ledger.py:68), so a model-validated event never has a non-dict payload, and `or {}` already covers None. The `isinstance(payload, dict)` guard only matters if the ledger HTTP response carries a raw list/str payload (a faulty or hostile ledger). No test pins that. LOW: either add a test with a raw non-dict payload served by a stub ledger, or drop the guard as dead code. The docstring claims "(or agent_id)" but agent_id is `str | None` by model and has no test; harmless.

## Conditions
1. LOW: pin or remove the payload-isinstance guard (M1).
2. Optional: rebase onto main (8 behind, clean).
