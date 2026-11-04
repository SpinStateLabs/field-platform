# Reviewer (lane A): C-1141 independent re-check of MERGE 9 (ma3), MERGE 12 (cb19), MERGE 15 (PR 431)

Claimed and done in one pass; no claim or report named C-1141 at the fetch (only restock and groomer notes). Same method and gates as 20261104-0800-reviewer-laneA-c1200-merge16-23-audit.md. Read-only; counts and shas only.

| MERGE | to | G1 FF + commits | G2 identity | G3 verifier 16/16 names head | G4 verdict file naming each head (PASS wording) | G5 CI | G6 PR state |
|---|---|---|---|---|---|---|---|
| 9 ma3, PR 334 8bea8c4, 335 fc73f64, 347 8dae2b3 | c4ac8c14 | OK (13) | OK | OK (20261101-1928) | OK (c1053 for 334+335, q57 for 347), verdict dated before the verifier run | OK 7 each | OK closed, pointer comment on all 3 |
| 12 cb19, PR 381 d46e191, 341 192f410, 325 a585257 | b5826200 | OK (28) | OK | OK (20261101-2119) | OK (q37-q42 and lane17 q42 for 381, q22 for 341, q20 for 325), all earlier than the verifier | OK 7 each | OK closed, pointer on all 3 |
| 15 PR 431 | 05942b98 | OK (13) | OK | OK (20261102-1245) | OK (c1123 names 05942b98, dated 1150, before the 1245 verifier) | OK 14 | OK MERGED, mergeCommit = head |

Totals from the table: 3 merges x 6 gates = 18 cells, 18 OK, 0 failed. All three are fast-forwards with tips on origin/main; commits 13 + 28 + 13 = 54 (STATUS: 13, 28, 13); 0 nonconforming identities, including MERGE 12 where STATUS says one PR 381 commit was re-authored inside the batch (the range holds no non-noreply author or committer).

## Thin spots
- T1 LOW: ordering here rests on file-name timestamps; within each merge verdict < verifier, but earlier I found timestamps non-monotonic across days elsewhere (C-1200 report T1), so treat the order as MEDIUM.
- T2 LOW: CI is read now, not at push time. PR heads equal the STATUS shas for all 7 PRs (no head move since).
- T3 LOW: PR 431 has no closure comment (MERGED by GitHub on the same sha, so a pointer is not applicable).
- T4 INFO: STATUS MERGE 15 mentions "3 merges of main" inside the 13 commits; parent counts not inspected.
- Not re-run: suites; 16/16 is read from reports. C-1123 F3 Don ruling and the 334 C1 non-blocking item not re-examined.
