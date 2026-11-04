# Reviewer report: PR 633 @ 1e2c304e55246d6b872b0eec49bb8fc758e95f58 (sealed-ledger tests: GET /events limit keeps the newest N after the filters, S3-11)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). One commit on origin/main b963407a (the current tip); `git merge-tree --write-tree origin/main pr633` clean. Tests only: services/sealed-ledger/tests/test_events_limit.py (+104). Author and committer Don Hagell 13129187+dhagell@users.noreply.github.com, trailer Sonnet 5.5 (HIGH).

## Objections first
1. The sealed ledger is the audit record; a read endpoint whose `limit` returned the OLDEST n, or cut before filtering, would make an auditor's "the last N events of this agent" wrong without any error. The behaviours under test are exactly that class, so the mutants below target those first.
2. The tests use hand-built small ledgers (10 events, and the C2 support fixture `three_segments` for rotation); they show the semantics, not performance: `events()` still reads the whole snapshot and slices in memory (store.py `events`, `out[-limit:]`), so `limit` bounds the response size, not the work. Not a defect of the PR; stated so nobody reads "limit" as a cost bound.
3. The README promise "the last N matches globally" and the code agree; across segments the global cut depends on `snap.indexed_events()` ordering; the rotation tests cover three segments with 11 events.

## Verified (run by me)
- Baseline on the exact head: tests/test_events_limit.py 19 passed (relative PYTHONPATH with every service's src and `tests` for the `ledger_c2_support` helper).
- Code read: store.py `events` filters first (`EventFilter.matches`) and then keeps `out[-limit:]`; api.py `list_events` declares `limit: int | None = Query(None, ge=1, le=10_000)` and passes it through; the service installs the field-core validation handler (api.py:273), which is why a rejected value is not echoed.

## Mutants (mutations of sealed_ledger/store.py and api.py; scratch worktree on the head; baseline 19 passed; kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| L1 | limit keeps the OLDEST n | 6 failed | yes |
| L2 | limit applied before the filters | 2 failed | yes |
| L3 | off by one, n+1 | 6 failed | yes |
| L4 | off by one, n-1 | 5 failed | yes |
| L5 | limit ignored | 6 failed | yes |
| L6 | result in descending order | 7 failed | yes |
| B1 | lower bound ge=1 -> ge=0 | 1 failed | yes |
| B2 | lower bound ge=1 -> ge=2 | 1 failed | yes |
| B3 | upper bound 10000 -> 10001 | 1 failed | yes |
| B4 | upper bound 10000 -> 9999 | 2 failed | yes |
| B5 | bounds removed | 6 failed | yes |
| B6 | limit declared as a string | 18 failed | yes |
| E1 | validation handler not installed (a rejected value echoed) | 3 failed | yes |
| A1 | route passes limit+1 to the store | 6 failed | yes |
| A2 | route drops the `since` filter | 1 failed | yes |
| A3 | route drops the `agent_id` filter | 2 failed | yes |
Totals counted from the table: 16 valid mutants, 16 killed, 0 survived. Excluded: my L7 (`limit=None` handling) was written as a no-op (`out = out`), so it is an equivalent mutant of my own making (it passed 19, as it must); my planned "per-segment cut" mutant (L8) was not built because the cut lives in the snapshot ordering, not in a line I could change cleanly, so the rotation test `test_across_a_rotated_ledger_the_cut_is_global` is read, not mutation-checked by me. No survivor to run against the suite.

## Findings
- F-S311-1 LOW: the global-across-rotation behaviour is pinned by tests I could read but not mutate (above); a builder with a per-segment slicing mutant could confirm.
- F-S311-2 LOW: objection 2; document that `limit` bounds the response, not the read.

## Verdict: PASS on 1e2c304e55246d6b872b0eec49bb8fc758e95f58
Head frozen; LOWs go in a NEW PR. Tests only but not docs: CI green and the full GX10 run on this exact head per the coordinator procedure. Not run by me: CI, GX10.
