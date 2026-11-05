# Review PR #784 (ops-console: wrong-shaped ledger events answer is a fixed 502, S8-26) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `9b1e5039f00c2a129cac0272dec7dd29cb57a005` (draft, base main). Optional LOWs go in a NEW PR.

## Facts (HIGH, read from the head)
- 1 commit, 3 files: ops_console/api.py (+19), tests/test_events_export_shapes.py (+86), docs/ENVIRONMENT.md (three cite renumberings, checked: api.py:472 FIELD_CROSSWALK_URL, :478 FIELD_LIFECYCLE_URL, :480 FIELD_ATTEST_URL all match the head). Nothing under .github/. Author AND committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- `_events_shape_ok` (list of dicts whose `payload` is a dict or null/absent) is applied inside `_ledger_events` after the status check, so `/api/events` and both exports share it. A bad shape is a fixed 502 whose text never contains the ledger body. Refuse-whole-answer (not skip) is the right choice for evidence exports. Only adds a refusal.
- tests/test_events_export_shapes.py: 41 passed on the head. Full ops-console suite (PR: 484 passed, one slow file deselected) not run by me.

## Mutants (api.py, one at a time, restored after each)
| # | Mutant | Result |
|---|--------|--------|
| M1 | shape check not called | RED |
| M2 | non-list accepted | RED |
| M3 | non-dict row skipped (accepted) | RED |
| M4 | any payload type accepted | RED |
| M5 | null/absent payload refused | RED |
| M6 | 502 body echoes the ledger data | RED |
| M7 | status 500 instead of 502 | RED |
| M8 | upstream-status relay line removed (shape check only) | SURVIVED |
Totals counted from the table: 8 mutants, 7 RED, 1 SURVIVED.

## LOWs (optional, new PR)
1. M8: the test for "an upstream error status still maps to an error" only asserts an error, not the mapped code, so replacing the status relay with the shape refusal passes. Assert the exact relayed status (for example a 503 stays 503).
2. Overlap with S5-20 and S7-27 (#752) on helpers in this file (author notes it); merge order is the coordinator's.
