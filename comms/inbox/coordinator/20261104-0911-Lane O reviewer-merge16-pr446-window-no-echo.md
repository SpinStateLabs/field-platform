# Lane O reviewer: MERGE 16 (PR 446 head itself, C-1154; main 05942b98 to 4f731ee9; 1 commit), ROLE-LOOP FALLBACK, read-only post-merge review. UNVERIFIED (cloud, no GX10)

VERDICT: PASS WITH CONDITIONS (retroactive; already on main), naming the merged head 4f731ee9. Lane B (attestation-reporter). One commit touching services/attestation-reporter/src/attestation_reporter/window.py (+19/-4) and tests/test_window_422_no_echo_c1154.py (+105); author and committer Don Hagell noreply (git log, HIGH). STATUS MERGE 16 cites Lane 7 Q-92 PASS naming this head; I did not re-read it and do not repeat it. I claimed MERGE 16 in a note (20261104-0908) before starting.

Objections first: (1) the new `_EXTENDED_DATE` rule refuses week, ordinal and basic ISO bounds that Python 3.11+ reads (`2026W44`, `20261031`, `2026-304`); a caller that sent those before now gets a 422 (a deliberate narrowing, Don's ruling on C-1052 F-3, read in the test docstring, HIGH). (2) the `name` of the bound (since or until) is still part of the message, which is code-supplied, not caller text (read, HIGH). (3) the regex only anchors the START (`match`, no end anchor); the rest of the string is left to `datetime.fromisoformat`, so a trailing-garbage value is refused by a later, different message (read, HIGH).

Run here (cloud, scratch worktree on 4f731ee9, relative PYTHONPATH of every service src and packages src): the new test file 34 passed (repeated 4 times, stable); whole attestation-reporter suite 255 passed. NOT run: the 16-suite set, CI.

Mutants on window.py (28 written; 1 of them was a no-op of mine that showed "killed" once and passed on 4 reruns, so it is excluded as a harness anomaly; 27 run in a scratch worktree on 4f731ee9; each against the new test file, survivors against the whole service suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 refusals repeat nothing the caller sent | 6 | 5 | 1 |
| B2 week, ordinal and basic forms are refused by name | 6 | 5 | 1 |
| B3 extended forms and the UTC reading are still accepted | 5 | 5 (1 by an older test) | 0 |
| B4 a good period is still accepted (one valid mutant besides the excluded no-op: 2 run) | 2 | 2 | 0 |
| B5 refusal messages are fixed text | 4 | 2 | 2 |
| B6 a bound with no UTC instant is refused | 4 | 2 | 2 |
| Total (counted from the rows) | 27 | 21 | 6 |
B4 has 2 runnable mutants (under 4).

Survivors (6): 2 equivalent, 4 real LOW pin gaps.
- Equivalent (read, MEDIUM): `search` instead of `match` on the extended-date rule (a leading-garbage value is still refused, by the later parse); `except (OverflowError,)` alone in the UTC branch (the ValueError of astimezone is not reachable here).
- F-O-m16-1: a PARTIAL echo survives: appending `text[:20]` to the "not a valid ISO 8601" message leaks the first 20 characters, and the test only searches for the whole 25-character marker, so a prefix echo passes (window.py, the second normalise_bound refusal). Real, LOW.
- F-O-m16-2: two messages are not pinned as fixed text: a length of the caller's value can be appended to "period is outside years 0001..9999" and to the "not a valid ISO 8601" bound message (the fixed-text test covers only the generic period and generic bound messages). Real, LOW (2 mutants).
- F-O-m16-3: the wording of the no-UTC-instant refusal is unpinned: replacing it with the generic "not a valid" text survives (the test checks the status and the absence of the value only). Real, LOW.

CONDITIONS (none blocking; on main): C1 a tests-only card for F-O-m16-1..3 (use a marker whose every 8-character slice is searched, not only the whole marker). C2 coordinator: C-1200 (meta audit of MERGE 16 to 23) is a card for Lane 14, 15 or 17; this report is an independent post-merge read of MERGE 16 only and does not close it.

Tokens/cost line: not available to me. I do not know.
