FROM: reviewer Lane 15 (cloud-reviewer). RE: queue empty; polling every 5 minutes.

No OPEN cloud-reviewer cards remain except the two held for Don (C-18, C-605). Taking new cards as they appear.

Things the coordinator should act on (details in the reports named):
1. Main moved to acaf5f2: batch BZ2 landed. PR 386 (BZ) and PR 389 (BZ2) are now duplicates of main: close both (C-955, C-965).
2. The compose stack (345, 353, 370, 385, 387, 391) conflicts with main only because of the duplicate bind-source commit; a rebase onto acaf5f2 succeeds and drops it (PR 391 rebased: 8 commits, 1054 tests of seven compose files pass) (C-976, C-987).
3. MCP write tier: the design note's rulings part 3 records attest as Tier 3 and Tier 2 as seven tools (PR 380 e17ea86 matches); PR 384 still ships eight (attest). The queue cards (C-902, C-941) say the ruling is still owed. The two records conflict: Don must confirm before either merges (C-947, C-954, C-981). Both heads still carry C-869 F-1 to F-3.
4. Moved heads since my earlier reports: PR 388 (now 5933066, tests for C-939 F-C388-3), PR 369 (now a469a60, the internal-path tie test), PR 379 (a020c33), PR 382 (5be16e6), PR 355 (640e1bd), PR 325 (2ab0e8a), PR 322 (1ce17e6), PR 360 (c5fddb5), PR 381 (f083ed2). Each re-reviewed on its head in the reports C-957 to C-993.
5. Open items needing a ruling or a card: attest (above); STATE.md still carries four one-hour soak lines (C-978, C-989); a approval-in-chat sentence for deploy sections 2 and 5 of the runbook (C-870 C4, C-970); the same-generation re-admit in the retired-key memory (C-847 F-C847-1, PR 355); bypass_operator_list on a prefixed verifier row (C-958); the HTTP 422 echo of a non-text signer (PR 366, C-986).
6. Sweeps C-968 and C-969 (merge readiness against acaf5f2) are in their reports; PR 362 conflicts with main on two test files already landed (rebase or close); 348 and 359 conflict in docs/ENVIRONMENT.md.
7. Corrections I appended to my own reports are inside the files (C-906, C-908, C-913, C-950, C-958, C-986).

No GX10 run, no CI read: every report is UNVERIFIED as the card says.
