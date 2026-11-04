# Reviewer (lane A): C-1200 independent re-check of MERGE 16 to MERGE 23 (counts and shas only)

Method: git (origin/main, origin/comms at fetch time), gh pr view, grep of the verifier and verdict files. Read-only. 6 gates per merge: G1 FF + commit count equals STATUS; G2 all commits Don Hagell noreply author AND committer; G3 verifier report exists, names the head, says 16/16; G4 reviewer verdict file naming the head; G5 CI SUCCESS on the PR head(s) (gh, current); G6 PR state: closed with pointer comment (batch merges) or MERGED on the same sha (PR-head merges).

| MERGE | to | G1 (commits) | G2 | G3 | G4 | G5 | G6 |
|---|---|---|---|---|---|---|---|
| 16 PR 446 | 4f731ee9 | OK (1) | OK | OK | OK (q92) | OK | OK merged, mergeCommit = head |
| 17 cb25 PR 438, 433 | 40aec372 | OK (5) | OK | OK | OK (c1124, c1126) | OK | OK pointer on both |
| 18 cb26 PR 447 | b39287c1 | OK (1) | OK | OK | OK (Q-93, Lane 17) | OK | OK pointer |
| 19 PR 442 | 6385f877 | OK (3) | OK | OK | OK (q102) | OK | OK merged, mergeCommit = head |
| 20 PR 461 | cddca526 | OK (3) | OK | OK | OK (q107) | OK | OK merged, mergeCommit = head |
| 21 cb28 PR 459 | c356e205 | OK (2) | OK | OK | OK (q105) | OK | OK pointer |
| 22 PR 470 | 4ef319cc | OK (5) | OK | OK | OK (q116) | OK | OK merged, mergeCommit = head |
| 23 s2q PR 440, 448, 469 | 793481f3 | OK (6) | OK | OK | OK (heads named in 7, 5, 3 inbox files) | OK | OK pointer on all three |

Totals from the table: 8 merges x 6 gates = 48 cells, 48 OK, 0 failed. Every step is a fast-forward (ancestor check), all 8 new tips are on origin/main, 26 commits in total (1+5+1+3+3+2+5+6), 0 nonconforming identities.

## Where the record is thin (not failures)
- T1 LOW: ORDER not proven. Inbox file-name timestamps are not monotonic (verifier B pr446 is 20261102-2335 but its verdict q92 is 20261103-0530; the cb25 verifier is 20261102-0605 yet MERGE 17 is dated 11-03), so I could not show each verdict and run preceded the push. I checked content and sha, not time.
- T2 LOW: verifier reports name the 8-character sha only (grep matched the short form), not the full 40.
- T3 LOW: G5 reads CI NOW (7 checks on batch PRs, 14 on PR-head merges, all SUCCESS), not at push time; "no head move" is checked only for PRs 438, 433, 447, 459 (current heads equal the STATUS shas) and PR-head merges (head = mergeCommit). For PRs 440, 448, 469 STATUS gives no head; I only confirmed the head sha appears in verdict files.
- T4 LOW: STATUS says MERGE 22 has "1 merge of main" inside its 5 commits; I did not inspect parent counts.
- T5 INFO: Q-93 and C-1126 verdicts are Lane 17 local Windows runs ("NOT a GX10"); the GX10 gate rests on the batch verifier runs. Lane 15 claimed Q-93 then withdrew (0715).
- Not re-run: no suite was re-run; 16/16 is read from the reports.
