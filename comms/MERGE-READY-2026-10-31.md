# field-platform merge-readiness table

- Repo: SpinStateLabs/field-platform (public). Read-only build: nothing merged, pushed or commented.
- main head: `acaf5f241f00754442c7adbbb0290769dbfe52c5` (acaf5f2, batch CA). comms head read: `f33d3b3738deb3766dad0277f4b2b5785fb5da77` (commit time 2026-10-31T11:32-04:00).
- Data time: `gh pr list` and fetch at Sat 2026-10-31 ~17:03 (system clock). Inbox file names carry lane-clock dates up to 20261109; not used as wall time.
- Open PRs: 81 (drafts 79; non-draft: 368, 380).
- Rules: comms/PROTOCOL.md as briefed. "behind main N" = head does not contain acaf5f2 (`git merge-base --is-ancestor`), N from `git rev-list --count head..main`; GitHub still reports most of these CLEAN because branch protection does not require up-to-date, so CLEAN alone is not "rebased on current main". HOLD source: tasks/DECISIONS-FOR-DON.md on origin/comms (PR 57: Don lifted the review hold but still decides the merge).
- Conventions: cloud (Lane 14/15) verdicts are listed as verdicts (independent reviewer lanes) but never count as GX10. A PASS WITH CONDITIONS on the current head = "conditions open" unless a later PASS on the same head exists. Builder-reported runs on the exact head (16 "== " suites, 0 failed) count as GX10; merged-state or partial-suite runs do not. "design-" reports count as reviewer verdicts; groomer reads do not.

## Counts per class (primary reason; every reason is listed in the state column)

| Class | Count | PRs |
|---|---|---|
| READY | 0 | - |
| READY-EXCEPT-REBASE | 3 | 358, 361, 366 |
| HOLD | 1 | 57 |
| SUPERSEDED/DUPLICATE | 12 | 305, 308, 315, 318, 327, 330, 340, 345, 353, 370, 385, 391 |
| DIRTY | 3 | 326, 359, 362 |
| STACKED | 3 | 380, 387, 395 |
| CI RED | 1 | 297 |
| VERDICT FAIL | 1 | 371 |
| STALE HEAD | 13 | 331, 333, 335, 342, 348, 356, 369, 375, 378, 381, 388, 393, 394 |
| NO VERDICT | 13 | 334, 396, 397, 398, 399, 400, 401, 402, 403, 404, 405, 406, 407 |
| CONDITIONS OPEN | 20 | 336, 339, 341, 343, 344, 346, 347, 351, 352, 355, 360, 363, 365, 367, 368, 372, 373, 374, 377, 379 |
| NO GX10 | 11 | 316, 317, 322, 325, 332, 337, 338, 349, 382, 383, 392 |

READY-EXCEPT-REBASE: every gate met on the exact head except that the head is behind main. A rebase makes a new head that needs a fresh verdict and GX10, or the coordinator carries the source head in a patch-id batch (as batch CA did).

## Table (READY first, then by PR number; all NOT READY)

| PR | head | CI | merge state | reviewer verdict + file | GX10 + file | state |
|---|---|---|---|---|---|---|
| 57 | 30ac1e1 | 7/7 | CLEAN (draft) | C-843 PASS WITH CONDITIONS on 30ac1e1 (do not arm); cloud C-843 recheck PWC on 30ac1e1 [`comms/inbox/coordinator/20261106-0400-reviewer-c843-pr57-key-rotation-full.md`] | 17 suites, 0 failed on 30ac1e1 (reviewer C-843) [`comms/inbox/coordinator/20261106-0400-reviewer-c843-pr57-key-rotation-full.md`] | NOT READY: HOLD; conditions open; behind main 22: rebase |
| 297 | 3bb2510 | 6/7 | UNSTABLE (draft) | C-473 PASS on 3bb2510 [`comms/inbox/coordinator/20261102-0600-reviewer-c473-pr297-lessons.md`] | none found | NOT READY: CI red (tests 3.12); no GX10; behind main 28: rebase |
| 305 | b484e7d | 7/7 | DIRTY (draft) | PWC on b484e7d; cloud C-972: should not merge (duplicate of 308) [`comms/inbox/coordinator/20261102-1130-reviewer-pr305-phase-e-words.md`] | none found | NOT READY: duplicate of PR 308; DIRTY; conditions open; no GX10; behind main 27: rebase |
| 308 | fc8b363 | 7/7 | CLEAN (draft) | cloud C-972 PWC on fc8b363 (local verdict only on e881626: stale) [`comms/inbox/coordinator/20261031-0025-reviewer-c972-pr308-vs-pr305.md`] | none found | NOT READY: duplicate of PR 305; conditions open; no GX10; behind main 13: rebase |
| 315 | ba26a96 | 7/7 | CLEAN (draft) | C-509 PWC on ba26a96, NOT recommended (take PR 295 branch) [`comms/inbox/coordinator/20261102-2300-reviewer-c509-pr315-vs-pr295-branch.md`] | tools suite only on ba26a96 (C-509) [`comms/inbox/coordinator/20261102-2300-reviewer-c509-pr315-vs-pr295-branch.md`] | NOT READY: reviewer recommends not merging; conditions open; no GX10 (partial run only); behind main 18: rebase |
| 316 | 6ae698f | 7/7 | CLEAN (draft) | C-567 PASS (one non-blocking finding) on 6ae698f [`comms/inbox/coordinator/20261106-0900-reviewer-c567-c458-pr316-console-csp.md`] | merged state efddb75 only, not exact head [`comms/inbox/coordinator/20261106-0900-reviewer-c567-c458-pr316-console-csp.md`] | NOT READY: no GX10 (merged state only); behind main 18: rebase |
| 317 | 9cc5221 | 7/7 | CLEAN (draft) | cloud C-865/C-973 PASS and C-711 PASS on 9cc5221 (cloud only) [`comms/inbox/coordinator/20261105-0000-design-c711-pr317-rate-rounding.md`] | none found | NOT READY: no GX10; behind main 18: rebase |
| 318 | 4383a07 | 7/7 | CLEAN (draft) | cloud C-710 PWC on 4383a07 [`comms/inbox/coordinator/20261104-1830-reviewer-c710-pr318-delta-lint-aliases.md`] | none found | NOT READY: superseded by PR 381; conditions open; no GX10; behind main 18: rebase |
| 322 | 1ce17e6 | 7/7 | CLEAN (draft) | cloud C-957/C-960/C-993 PASS on 1ce17e6 (cloud only) [`comms/inbox/coordinator/20261031-0041-reviewer-c993-pr322-recheck.md`] | none found (builder: UNVERIFIED on GX10) [`comms/inbox/coordinator/20261030-2000-builder-lane1-c864.md`] | NOT READY: no GX10; behind main 17: rebase |
| 325 | 2ab0e8a | 7/7 | CLEAN (draft) | C-43 PASS WITH ONE LOW FINDING on 2ab0e8a (F-C325-1 left as proposed card) [`comms/inbox/coordinator/20261107-0700-reviewer-c43-deltas-pr381-pr325-pr388-pr392.md`] | merged state 38c39ec only [`comms/inbox/coordinator/20261107-0700-reviewer-c43-deltas-pr381-pr325-pr388-pr392.md`] | NOT READY: no GX10 (merged state only); behind main 17: rebase |
| 326 | da33a9a | 7/7 | DIRTY (draft) | C-729 PWC on da33a9a; C-791: none of the C-729 conditions closed; cloud C-791 FAIL [`comms/inbox/coordinator/20261105-0500-design-c791-pr326-conditions.md`] | none found | NOT READY: DIRTY; conditions open; no GX10; behind main 17: rebase |
| 327 | dc0fc85 | 7/7 | CLEAN (draft) | none on dc0fc85; cloud C-595: merge PR 322, close PR 327 [`comms/inbox/coordinator/20261103-1805-reviewer-c595-pr322-vs-pr327.md`] | none found | NOT READY: duplicate of PR 322; no verdict; no GX10; behind main 18: rebase |
| 330 | f0e9e70 | NONE | DIRTY (draft) | C-838 PWC on f0e9e70 [`comms/inbox/coordinator/20261105-2400-reviewer-c838-pr330-delta-f0e9e70.md`] | none found | NOT READY: superseded by PR 381; no CI runs; DIRTY; conditions open; no GX10; behind main 17: rebase |
| 331 | 4014720 | 3/7 | UNSTABLE (draft) | stale head: C-688 PWC on 1a45db0 (head 4014720) [`comms/inbox/coordinator/20261104-1000-reviewer-c688-pr331-anchors-parser.md`] | 16/0 on 4014720c (builder Lane 2) [`comms/inbox/coordinator/20261105-0100-builder-lane2-c715-c725.md`] | NOT READY: CI red (4 jobs); stale head; behind main 17: rebase |
| 332 | 0df2259 | 7/7 | CLEAN (draft) | C-614 PASS on 0df2259 (design lane) [`comms/inbox/coordinator/20261104-0200-design-c614-pr332-pr317-deltas.md`] | none found | NOT READY: no GX10; behind main 17: rebase |
| 333 | f34d092 | 7/7 | CLEAN (draft) | stale head: C-687 PWC / design PASS on 39f8636 (head f34d092) [`comms/inbox/coordinator/20261104-1100-design-c687-pr333-approver-cursor.md`] | 16/0 on f34d092d (builder Lane 2) [`comms/inbox/coordinator/20261105-0100-builder-lane2-c715-c725.md`] | NOT READY: stale head; behind main 17: rebase |
| 334 | 8bea8c4 | 7/7 | CLEAN (draft) | no reviewer verdict; groomer C-608 cloud read PASS on 8bea8c4 [`comms/inbox/coordinator/20261030-1526-groomer-c608-pr334-adr02-note.md`] | none found | NOT READY: no verdict; no GX10; behind main 13: rebase |
| 335 | fc73f64 | 7/7 | CLEAN (draft) | stale head: C-654 PWC on 2e00c73 (head fc73f64) [`comms/inbox/coordinator/20261104-0450-reviewer-c654-pr335-adr07-note.md`] | none found | NOT READY: stale head; no GX10; behind main 13: rebase |
| 336 | 08463bd | 7/7 | CLEAN (draft) | C-695 PWC on fe6c2be, delta read to 08463bd ("land 08463bd"); cond (b) ruled by Don 2026-11-05; others not verified closed [`comms/inbox/coordinator/20261104-2100-reviewer-c695-pr336-halt-client.md`] | 16/0 on 08463bd (builder) [`comms/inbox/coordinator/20261030-1649-builder-c811.md`] | NOT READY: conditions open; behind main 17: rebase |
| 337 | 72e8fae | 7/7 | CLEAN (draft) | C-694 PASS on 72e8fae (design lane) [`comms/inbox/coordinator/20261104-1500-design-c694-pr337-pr338-pr340-pr341-docs-deltas.md`] | none found | NOT READY: no GX10; behind main 13: rebase |
| 338 | f052a0e | 7/7 | CLEAN (draft) | C-694 PASS on f052a0e (design lane) [`comms/inbox/coordinator/20261104-1500-design-c694-pr337-pr338-pr340-pr341-docs-deltas.md`] | none found | NOT READY: no GX10; behind main 13: rebase |
| 339 | 0219998 | 7/7 | CLEAN (draft) | cloud C-458 PWC on 0219998 [`comms/inbox/coordinator/20261031-0106-reviewer-c458-pr316-pr314-pr339.md`] | none found (builder: UNVERIFIED on GX10) [`comms/inbox/coordinator/20261030-1700-builder-lane1-c673.md`] | NOT READY: conditions open; no GX10; behind main 13: rebase |
| 340 | 25ffdc1 | 7/7 | CLEAN (draft) | C-933 PASS on 25ffdc1 [`comms/inbox/coordinator/20261106-2200-reviewer-c933-pr340-integration-delta.md`] | test_deploy_docs.py only on 25ffdc1, not labelled light run [`comms/inbox/coordinator/20261106-2200-reviewer-c933-pr340-integration-delta.md`] | NOT READY: carried by batch PR 398; no GX10 (partial run only); behind main 13: rebase |
| 341 | f1d4dbb | 7/7 | CLEAN (draft) | C-1016 PWC on f1d4dbb [`comms/inbox/coordinator/20261107-2200-reviewer-c1016-pr341-delta.md`] | force-gateway suite only on f1d4dbb [`comms/inbox/coordinator/20261107-0900-reviewer-c1016-pr341-adr10-delta2.md`] | NOT READY: conditions open; no GX10 (partial run only); behind main 13: rebase |
| 342 | dd76873 | 7/7 | CLEAN (draft) | stale head: C-793 PWC on 697b8ec (head dd76873) [`comms/inbox/coordinator/20261105-0630-design-c793-pr342-conditions.md`] | none found (builder: not run) [`comms/inbox/coordinator/20261031-0300-builder-lane1-c1038.md`] | NOT READY: stale head; no GX10; behind main 17: rebase |
| 343 | e531734 | 7/7 | CLEAN (draft) | cloud C-979 PWC on e531734 [`comms/inbox/coordinator/20261031-0034-reviewer-c979-pr343-pip-scanner-shapes.md`] | none found | NOT READY: conditions open; no GX10; behind main 13: rebase |
| 344 | 627532e | 7/7 | CLEAN (draft) | cloud C-789/C-861 PWC on 627532e [`comms/inbox/coordinator/20261030-2024-reviewer-c861-pr344-newest-head.md`] | none found | NOT READY: conditions open; no GX10; behind main 13: rebase |
| 345 | f3787c9 | 7/7 | CLEAN (draft) | C-640 PWC on f3787c9 [`comms/inbox/coordinator/20261104-0400-reviewer-c640-pr345-compose-shared-keys.md`] | tools suite only on f3787c9 (C-640) [`comms/inbox/coordinator/20261104-0400-reviewer-c640-pr345-compose-shared-keys.md`] | NOT READY: superseded by PR 400; stacked on merged PR 328 branch test/compose-resolved-bind-c512; conditions open; no GX10 (partial run only); behind main 17: rebase |
| 346 | ef19210 | 8/8 | CLEAN (draft) | cloud C-868 PWC on ef19210 [`comms/inbox/coordinator/20261030-2040-reviewer-c868-pr346-commit-identity-ef19210.md`] | none found | NOT READY: conditions open; no GX10; behind main 13: rebase |
| 347 | 10dfdef | 7/7 | CLEAN (draft) | C-839 PWC on 10dfdef [`comms/inbox/coordinator/20261106-0800-reviewer-c839-pr347-edge-shapes-delta.md`] | 16/0 on 10dfdef (builder Lane 11) [`comms/inbox/coordinator/20261109-0950-builder-lane11-status-report.md`] | NOT READY: conditions open; behind main 13: rebase |
| 348 | 33a6e4b | 7/7 | CLEAN (draft) | stale head: C-936 PWC on 7d332d1 (head 33a6e4b) [`comms/inbox/coordinator/20261107-0200-reviewer-c936-pr348-ops-console-delta.md`] | none found (builder: not run) [`comms/inbox/coordinator/20261108-1500-builder-lane1-c504.md`] | NOT READY: stale head; no GX10; behind main 5: rebase |
| 349 | ba35c14 | 7/7 | CLEAN (draft) | C-43 PASS on ba35c14 [`comms/inbox/coordinator/20261106-1800-reviewer-c43-deltas-pr349-pr352-pr358-pr361.md`] | merged state bc2cb3b only (Lane 2 16/0 was on older 1e3dea5a) [`comms/inbox/coordinator/20261106-1800-reviewer-c43-deltas-pr349-pr352-pr358-pr361.md`] | NOT READY: no GX10 (merged state only); behind main 13: rebase |
| 351 | 310c409 | 7/7 | CLEAN (draft) | cloud C-956 PWC on 310c409 [`comms/inbox/coordinator/20261031-0000-reviewer-c956-pr351-newest-head.md`] | full run on 310c4099 (builder Lane 12) [`comms/inbox/coordinator/20261109-0200-builder-lane12-pr388-gx10.md`] | NOT READY: conditions open; behind main 13: rebase |
| 352 | 6f30657 | 7/7 | CLEAN (draft) | C-43 PASS WITH ONE OPEN ITEM on 6f30657 (commit authored as "Claude" still in branch) [`comms/inbox/coordinator/20261106-1800-reviewer-c43-deltas-pr349-pr352-pr358-pr361.md`] | none found (left out of merged state: conflicts with 358) | NOT READY: conditions open; no GX10; behind main 13: rebase |
| 353 | 5d5cbf7 | 7/7 | CLEAN (draft) | C-735 PWC on 5d5cbf7 [`comms/inbox/coordinator/20261105-0800-reviewer-c735-pr353-resolved-model-check.md`] | 16/0 on 5d5cbf73 (builder Lane 2) [`comms/inbox/coordinator/20261105-0100-builder-lane2-c715-c725.md`] | NOT READY: superseded by PR 400; stacked on 345; conditions open; behind main 17: rebase |
| 355 | 640e1bd | 7/7 | CLEAN (draft) | cloud C-962/C-988/C-1002 PWC on 640e1bd [`comms/inbox/coordinator/20261031-0054-reviewer-c1002-verify-f-c847-1.md`] | 16/0 on 640e1bd1 (builder Lane 13) [`comms/inbox/coordinator/20261106-1200-builder-lane13-c922-c923.md`] | NOT READY: conditions open; behind main 13: rebase |
| 356 | 3713e14 | 7/7 | CLEAN (draft) | stale head: C-1047 PWC on 3361e01 (head 3713e14) [`comms/inbox/coordinator/20261109-1300-reviewer-c1047-pr356-is-internal-host.md`] | 16/0 on 3713e14 (builder Lane 11) [`comms/inbox/coordinator/20261109-1200-builder-lane11-c1047-c1048-c1049-conditions.md`] | NOT READY: stale head; behind main 13: rebase |
| 358 | 07bd6d6 | 7/7 | CLEAN (draft) | C-43 PASS on 07bd6d6 [`comms/inbox/coordinator/20261106-1800-reviewer-c43-deltas-pr349-pr352-pr358-pr361.md`] | 16/0 on 07bd6d63 (builder Lane 13) [`comms/inbox/coordinator/20261105-1500-builder-lane13-conditions-c826-c827-c829-c832-c834.md`] | NOT READY: behind main 10: rebase |
| 359 | 8948389 | NONE | DIRTY (draft) | cloud C-863 PWC on 8948389 [`comms/inbox/coordinator/20261105-1800-reviewer-c863-pr359-read-caps-newest-head.md`] | 16/0 on 8948389c (builder Lane 13) [`comms/inbox/coordinator/20261030-2000-builder-lane13-gx10-results-c51-c98-c106-c128-c591-c616.md`] | NOT READY: no CI runs; DIRTY; conditions open; behind main 13: rebase |
| 360 | c5fddb5 | 7/7 | CLEAN (draft) | cloud C-963 PWC on c5fddb5 [`comms/inbox/coordinator/20261031-0013-reviewer-c963-pr360-burst-window.md`] | 16/0 on c5fddb54 (builder Lane 13) [`comms/inbox/coordinator/20261106-1200-builder-lane13-c922-c923.md`] | NOT READY: conditions open; behind main 13: rebase |
| 361 | 7525a93 | 7/7 | CLEAN (draft) | C-43 PASS on 7525a93 [`comms/inbox/coordinator/20261106-1800-reviewer-c43-deltas-pr349-pr352-pr358-pr361.md`] | full run on 7525a936 (builder Lane 12) [`comms/inbox/coordinator/20261109-0200-builder-lane12-pr388-gx10.md`] | NOT READY: behind main 13: rebase |
| 362 | b468f79 | 7/7 | DIRTY (draft) | cloud C-890 PWC on b468f79 [`comms/inbox/coordinator/20261030-2217-reviewer-c890-pr358-pr360-pr362-after-lane13.md`] | 16/0 on b468f792 (builder Lane 13) [`comms/inbox/coordinator/20261105-1500-builder-lane13-conditions-c826-c827-c829-c832-c834.md`] | NOT READY: DIRTY; conditions open; behind main 13: rebase |
| 363 | 02d1159 | 7/7 | CLEAN (draft) | cloud C-1050 PWC on 02d1159 (F-C1050-1 LOW, optional) [`comms/inbox/coordinator/20261031-1359-reviewer-c1050-pr363-video-script-delta.md`] | 16/0 on 02d1159 (builder Lane 11) [`comms/inbox/coordinator/20261107-2000-builder-lane11-pr363-c937.md`] | NOT READY: conditions open; behind main 13: rebase |
| 365 | d570c31 | 7/7 | CLEAN (draft) | cloud C-891 PWC on d570c31 [`comms/inbox/coordinator/20261030-2224-reviewer-c891-pr365-pr367-after-lane13.md`] | 16/0 on d570c31d (builder Lane 13) [`comms/inbox/coordinator/20261105-1500-builder-lane13-conditions-c826-c827-c829-c832-c834.md`] | NOT READY: conditions open; behind main 13: rebase |
| 366 | 3436007 | 7/7 | CLEAN (draft) | C-841 PASS (one non-blocking finding) on 3436007 [`comms/inbox/coordinator/20261105-2335-reviewer-c841-pr366-delta-signer-message.md`] | full run on 3436007e (builder Lane 12) [`comms/inbox/coordinator/20261109-0200-builder-lane12-pr388-gx10.md`] | NOT READY: behind main 13: rebase |
| 367 | 46bc0d9 | 7/7 | CLEAN (draft) | cloud C-891 PWC on 46bc0d9 [`comms/inbox/coordinator/20261030-2224-reviewer-c891-pr365-pr367-after-lane13.md`] | 16/0 on 46bc0d9a (builder Lane 13) [`comms/inbox/coordinator/20261105-1500-builder-lane13-conditions-c826-c827-c829-c832-c834.md`] | NOT READY: conditions open; behind main 13: rebase |
| 368 | 1f7f61f | 7/7 | CLEAN | C-775 PWC on 1f7f61f; cloud C-790 PWC [`comms/inbox/coordinator/20261105-0600-reviewer-c775-pr368-mcp-pr1.md`] | every CI suite green on 1f7f61f (reviewer C-775) [`comms/inbox/coordinator/20261105-0600-reviewer-c775-pr368-mcp-pr1.md`] | NOT READY: conditions open; behind main 13: rebase |
| 369 | 6f1fd7d | 7/7 | CLEAN (draft) | stale head: C-43 PWC on a469a60 (head 6f1fd7d) [`comms/inbox/coordinator/20261108-0300-reviewer-c43-deltas-pr369-pr381-pr391-pr382.md`] | 16/0 on 6f1fd7d0 (builder Lane 12) [`comms/inbox/coordinator/20261108-0900-builder-lane12-pr369-c1031.md`] | NOT READY: stale head; behind main 10: rebase |
| 370 | 1381b56 | 7/7 | CLEAN (draft) | cloud C-787 FAIL on 1381b56 [`comms/inbox/coordinator/20261030-1945-reviewer-c787-pr370-compose-conditions.md`] | 16/0 on 1381b565 (builder Lane 2) [`comms/inbox/coordinator/20261105-0100-builder-lane2-c715-c725.md`] | NOT READY: superseded by PR 400; stacked on 353; verdict FAIL; behind main 17: rebase |
| 371 | 8eb5c87 | 7/7 | CLEAN (draft) | cloud C-786/C-807/C-860/C-883 FAIL on 8eb5c87 [`comms/inbox/coordinator/20261030-2124-reviewer-c883-pr371-id-grammar-containment.md`] | 16/0 on 8eb5c872 (builder Lane 13) [`comms/inbox/coordinator/20261030-2000-builder-lane13-gx10-results-c51-c98-c106-c128-c591-c616.md`] | NOT READY: verdict FAIL; behind main 10: rebase |
| 372 | 1b8f9e3 | 7/7 | CLEAN (draft) | cloud C-884 PWC on 1b8f9e3 [`comms/inbox/coordinator/20261030-2135-reviewer-c884-pr372-newest-head.md`] | none found (builder: partial suites) [`comms/inbox/coordinator/20261030-2359-builder-lane1-c855-pr372.md`] | NOT READY: conditions open; no GX10; behind main 10: rebase |
| 373 | 8c3cfb5 | 7/7 | CLEAN (draft) | cloud C-856 PWC on 8c3cfb5 [`comms/inbox/coordinator/20261105-1600-reviewer-c856-pr373-spend-totals-after-c784.md`] | spend-governor only on 8c3cfb5e (full set was on 2f7450a1) [`comms/inbox/coordinator/20261030-2000-builder-lane13-gx10-results-c51-c98-c106-c128-c591-c616.md`] | NOT READY: conditions open; no GX10 (partial run only); behind main 10: rebase |
| 374 | b97d35f | 7/7 | CLEAN (draft) | cloud C-983 PWC on b97d35f [`comms/inbox/coordinator/20261031-0039-reviewer-c983-pr374-internal-secret-recheck.md`] | full run on b97d35fc (builder Lane 12) [`comms/inbox/coordinator/20261109-0200-builder-lane12-pr388-gx10.md`] | NOT READY: conditions open; behind main 10: rebase |
| 375 | b5e74e2 | 7/7 | CLEAN (draft) | stale head: C-1048 PWC on 178af63 (head b5e74e2) [`comms/inbox/coordinator/20261109-1100-reviewer-c1048-pr375-delta.md`] | 16/0 on b5e74e2 (builder Lane 11) [`comms/inbox/coordinator/20261109-1200-builder-lane11-c1047-c1048-c1049-conditions.md`] | NOT READY: stale head; behind main 10: rebase |
| 377 | dfceabc | 7/7 | CLEAN (draft) | cloud C-875 PWC on dfceabc [`comms/inbox/coordinator/20261030-2051-reviewer-c875-pr377-ntfy-runbook.md`] | none found | NOT READY: conditions open; no GX10; behind main 10: rebase |
| 378 | 1519000 | 7/7 | CLEAN (draft) | stale head: C-874 PWC on 6727f5b (head 1519000) [`comms/inbox/coordinator/20261105-2300-reviewer-c874-pr378-capstone-hardening-dates.md`] | none found | NOT READY: stale head; no GX10; behind main 10: rebase |
| 379 | f958cab | 7/7 | CLEAN (draft) | cloud C-1006 PWC on f958cab [`comms/inbox/coordinator/20261031-0057-reviewer-c1006-pr379-current-head.md`] | none found (builder: not run) [`comms/inbox/coordinator/20261031-0100-builder-lane1-c970-pr379.md`] | NOT READY: conditions open; no GX10; behind main 10: rebase |
| 380 | b8af78f | 7/7 | CLEAN | stale head: C-869 PWC on 7551327 (head b8af78f) [`comms/inbox/coordinator/20261106-1000-reviewer-c869-pr380-mcp-pr2-writes.md`] | none found | NOT READY: carries PR 368 commits (stacked on 368); stale head; no GX10; behind main 13: rebase |
| 381 | 59dc283 | 7/7 | CLEAN (draft) | stale head: C-43 PASS on 8c781bb (head 59dc283) [`comms/inbox/coordinator/20261108-0300-reviewer-c43-deltas-pr369-pr381-pr391-pr382.md`] | none found (builder: partial suites) [`comms/inbox/coordinator/20261031-0300-builder-lane1-c1041-pr381-59dc283.md`] | NOT READY: stale head; no GX10; behind main 10: rebase |
| 382 | 0dde283 | 7/7 | CLEAN (draft) | C-43 PASS on 0dde283 [`comms/inbox/coordinator/20261108-0300-reviewer-c43-deltas-pr369-pr381-pr391-pr382.md`] | merged state 61fac6d only [`comms/inbox/coordinator/20261108-0300-reviewer-c43-deltas-pr369-pr381-pr391-pr382.md`] | NOT READY: no GX10 (merged state only); behind main 10: rebase |
| 383 | defb7ea | 7/7 | CLEAN (draft) | C-43 PASS on defb7ea (C-942 confirms) [`comms/inbox/coordinator/20261107-0300-reviewer-c939-c940-c942-pr391-pr388-pr383.md`] | merged state 22a320d only (builder: not run) [`comms/inbox/coordinator/20261106-1600-reviewer-c43-pr383-delta-pr388.md`] | NOT READY: no GX10 (merged state only); behind main 10: rebase |
| 385 | 112cf16 | 7/7 | CLEAN (draft) | cloud C-952 PWC on 112cf16 [`comms/inbox/coordinator/20261030-2358-reviewer-c952-pr385-after-c899.md`] | none found | NOT READY: superseded by PR 400; stacked on 370; conditions open; no GX10; behind main 17: rebase |
| 387 | 98de2c7 | 7/7 | CLEAN (draft) | stale head: C-1049 PWC on 65a37a0 (head 98de2c7) [`comms/inbox/coordinator/20261109-1130-reviewer-c1049-pr387-delta.md`] | 16/0 on 98de2c7 (builder Lane 11) [`comms/inbox/coordinator/20261109-1200-builder-lane11-c1047-c1048-c1049-conditions.md`] | NOT READY: PR 400 re-cut lacks 65a37a0..98de2c7; stacked on 385; stale head; behind main 17: rebase |
| 388 | b59068b | 7/7 | CLEAN (draft) | stale head: C-43 PASS on 5933066 (head b59068b) [`comms/inbox/coordinator/20261107-0700-reviewer-c43-deltas-pr381-pr325-pr388-pr392.md`] | full run on b59068b4 (builder Lane 12) [`comms/inbox/coordinator/20261109-0200-builder-lane12-pr388-gx10.md`] | NOT READY: stale head; behind main 5: rebase |
| 391 | 647786e | 7/7 | DIRTY (draft) | C-1030 PWC on 647786e; C-43 PWC (stack no longer merges, F-C391-1) [`comms/inbox/coordinator/20261108-0200-reviewer-c1030-pr391-delta.md`] | none found | NOT READY: superseded by PR 400; DIRTY; stacked on 387; conditions open; no GX10; behind main 17: rebase |
| 392 | 36c0d55 | 7/7 | CLEAN (draft) | C-43 PASS on 36c0d55; cloud C-989 PWC on 36c0d55 (STATE.md soak lines) not resolved [`comms/inbox/coordinator/20261107-0700-reviewer-c43-deltas-pr381-pr325-pr388-pr392.md`] | merged state 38c39ec only; no light run on 36c0d55 [`comms/inbox/coordinator/20261107-0700-reviewer-c43-deltas-pr381-pr325-pr388-pr392.md`] | NOT READY: no GX10 (merged state only) |
| 393 | 2264972 | 7/7 | CLEAN (draft) | stale head: C-1027 PWC on ce328a1 (head 2264972) [`comms/inbox/coordinator/20261108-0100-reviewer-c1027-pr393-soak-new-event.md`] | none found | NOT READY: stale head; no GX10 |
| 394 | cf335e6 | 7/7 | CLEAN (draft) | stale head: cloud C-1034 FAIL on 63ed5b2 (head cf335e6) [`comms/inbox/coordinator/20261031-0133-reviewer-c1034-pr394-validation-422-no-echo.md`] | 16/0 on cf335e6a (builder Lane 12) [`comms/inbox/coordinator/20261108-1300-builder-lane12-pr394-c1037.md`] | NOT READY: stale head |
| 395 | 7ab62d5 | 7/7 | CLEAN (draft) | stale head: C-1029 PWC on 32e712d (head 7ab62d5) [`comms/inbox/coordinator/20261108-0200-reviewer-c1029-pr395-federation-contract-ledger.md`] | none found (builder: not run) [`comms/inbox/coordinator/20261108-0300-builder-lane1-c1029-pr395.md`] | NOT READY: carries PR 322 commits (stacked on 322); stale head; no GX10; behind main 17: rebase |
| 396 | 2d830e9 | 7/7 | CLEAN (draft) | none found | none found (builder: not run) [`comms/inbox/coordinator/20261107-0210-builder-lane1-c760.md`] | NOT READY: no verdict; no GX10 |
| 397 | 68eab2f | 7/7 | CLEAN (draft) | none found | none found (builder: not run) [`comms/inbox/coordinator/20261107-0200-builder-lane1-c758.md`] | NOT READY: no verdict; no GX10 |
| 398 | 3a936d9 | 7/7 | CLEAN (draft) | none on batch head 3a936d9; source verdict C-933 PASS on PR 340 25ffdc1 (per PR body) [`comms/inbox/coordinator/20261106-2200-reviewer-c933-pr340-integration-delta.md`] | none found on 3a936d9 | NOT READY: no verdict; no GX10 |
| 399 | 6b6bc98 | 7/7 | CLEAN (draft) | none found | none found (builder: not run) [`comms/inbox/coordinator/20261107-0200-builder-lane1-c757.md`] | NOT READY: no verdict; no GX10 |
| 400 | fe2eed3 | 7/7 | CLEAN (draft) | none found (re-cut of 345/353/370/385/387@d4902a0/391; source verdicts are on old heads) | none found (PR body points to a builder note; no comms note names fe2eed3) | NOT READY: draft-with-no-reports; no GX10 |
| 401 | 8796131 | 7/7 | CLEAN (draft) | none found | 16/0 on 8796131 (builder Lane 13) [`comms/inbox/coordinator/20261031-1130-builder-lane13-c1046.md`] | NOT READY: no verdict |
| 402 | c0e6c02 | 7/7 | CLEAN (draft) | none found | 16/0 on c0e6c02 (builder Lane 11) [`comms/inbox/coordinator/20261109-1030-builder-lane11-c1043.md`] | NOT READY: no verdict |
| 403 | 1dd2b37 | 7/7 | CLEAN (draft) | none found | 16/0 on 1dd2b37 (builder Lane 11) [`comms/inbox/coordinator/20261109-1055-builder-lane11-c1044.md`] | NOT READY: no verdict |
| 404 | de74b3b | 7/7 | CLEAN (draft) | none found | 16/0 on de74b3b plus retro suite 229 passed (builder Lane 12) [`comms/inbox/coordinator/20261031-1100-builder-lane12-c1045-pr404.md`] | NOT READY: no verdict |
| 405 | f101fe7 | 7/7 | CLEAN (draft) | none found | none found (builder: not run) [`comms/inbox/coordinator/20261108-1500-builder-lane1-c504.md`] | NOT READY: no verdict; no GX10 |
| 406 | a40e6da | 7/7 | CLEAN (draft) | none found | none found (builder: not run) [`comms/inbox/coordinator/20261109-1500-builder-lane1-c1042.md`] | NOT READY: no verdict; no GX10 |
| 407 | bdf0de3 | 7/7 | CLEAN (draft) | none found | none found (builder: not run) [`comms/inbox/coordinator/20261031-1508-builder-lane1-c505.md`] | NOT READY: no verdict; no GX10 |

## Reviewer cards needed (no verdict on the current head; superseded/duplicate/HOLD omitted)

- PR 331 @4014720: code; stale head: C-688 PWC on 1a45db0 (head 4014720)
- PR 333 @f34d092: code; stale head: C-687 PWC / design PASS on 39f8636 (head f34d092)
- PR 334 @8bea8c4: docs
- PR 335 @fc73f64: docs; stale head: C-654 PWC on 2e00c73 (head fc73f64)
- PR 342 @dd76873: code; stale head: C-793 PWC on 697b8ec (head dd76873)
- PR 348 @33a6e4b: code; stale head: C-936 PWC on 7d332d1 (head 33a6e4b)
- PR 356 @3713e14: code; stale head: C-1047 PWC on 3361e01 (head 3713e14)
- PR 369 @6f1fd7d: code; stale head: C-43 PWC on a469a60 (head 6f1fd7d)
- PR 375 @b5e74e2: code; stale head: C-1048 PWC on 178af63 (head b5e74e2)
- PR 378 @1519000: docs; stale head: C-874 PWC on 6727f5b (head 1519000)
- PR 380 @b8af78f: code; stale head: C-869 PWC on 7551327 (head b8af78f)
- PR 381 @59dc283: code; stale head: C-43 PASS on 8c781bb (head 59dc283)
- PR 387 @98de2c7: test; stale head: C-1049 PWC on 65a37a0 (head 98de2c7)
- PR 388 @b59068b: test; stale head: C-43 PASS on 5933066 (head b59068b)
- PR 393 @2264972: docs; stale head: C-1027 PWC on ce328a1 (head 2264972)
- PR 394 @cf335e6: code; stale head: cloud C-1034 FAIL on 63ed5b2 (head cf335e6)
- PR 395 @7ab62d5: code; stale head: C-1029 PWC on 32e712d (head 7ab62d5)
- PR 396 @2d830e9: docs
- PR 397 @68eab2f: code
- PR 398 @3a936d9: docs
- PR 399 @6b6bc98: code
- PR 400 @fe2eed3: test
- PR 401 @8796131: test
- PR 402 @c0e6c02: test
- PR 403 @1dd2b37: test
- PR 404 @de74b3b: test
- PR 405 @f101fe7: code
- PR 406 @a40e6da: test
- PR 407 @bdf0de3: test

Also needed as fresh delta verdicts once conditions are closed: every "conditions open" row.

## GX10 runs needed (no qualifying run on the exact head; superseded/duplicate/HOLD omitted)

- PR 297 @3bb2510: docs only, light run allowed ("light run, docs only")
- PR 316 @6ae698f: full 16-suite run
- PR 317 @9cc5221: full 16-suite run
- PR 322 @1ce17e6: full 16-suite run
- PR 325 @2ab0e8a: full 16-suite run
- PR 326 @da33a9a: full 16-suite run
- PR 332 @0df2259: full 16-suite run
- PR 334 @8bea8c4: docs only, light run allowed ("light run, docs only")
- PR 335 @fc73f64: docs only, light run allowed ("light run, docs only")
- PR 337 @72e8fae: docs only, light run allowed ("light run, docs only")
- PR 338 @f052a0e: full 16-suite run
- PR 339 @0219998: full 16-suite run
- PR 341 @f1d4dbb: full 16-suite run
- PR 342 @dd76873: full 16-suite run
- PR 343 @e531734: full 16-suite run
- PR 344 @627532e: full 16-suite run
- PR 346 @ef19210: full 16-suite run
- PR 348 @33a6e4b: full 16-suite run
- PR 349 @ba35c14: full 16-suite run
- PR 352 @6f30657: full 16-suite run
- PR 372 @1b8f9e3: full 16-suite run
- PR 373 @8c3cfb5: full 16-suite run
- PR 377 @dfceabc: docs only, light run allowed ("light run, docs only")
- PR 378 @1519000: docs only, light run allowed ("light run, docs only")
- PR 379 @f958cab: full 16-suite run
- PR 380 @b8af78f: full 16-suite run
- PR 381 @59dc283: full 16-suite run
- PR 382 @0dde283: docs only, light run allowed ("light run, docs only")
- PR 383 @defb7ea: full 16-suite run
- PR 392 @36c0d55: docs only, light run allowed ("light run, docs only")
- PR 393 @2264972: docs only, light run allowed ("light run, docs only")
- PR 395 @7ab62d5: full 16-suite run
- PR 396 @2d830e9: docs only, light run allowed ("light run, docs only")
- PR 397 @68eab2f: full 16-suite run
- PR 398 @3a936d9: docs only, light run allowed ("light run, docs only")
- PR 399 @6b6bc98: full 16-suite run
- PR 400 @fe2eed3: full 16-suite run
- PR 405 @f101fe7: full 16-suite run
- PR 406 @a40e6da: full 16-suite run
- PR 407 @bdf0de3: full 16-suite run

## Builder / coordinator action needed

- PR 57: C-1024 conditions; rotation _soak to 30 min (Don, 2026-10-31)
- PR 297: diagnose or re-run the red CI job; rebase on main acaf5f2 (behind 28) or carry in a batch
- PR 305: coordinator: pick 305 or 308; DIRTY: resolve conflicts / rebase
- PR 308: coordinator: pick 305 or 308
- PR 315: coordinator: close or port to the PR 295 line
- PR 316: rebase on main acaf5f2 (behind 18) or carry in a batch
- PR 317: rebase on main acaf5f2 (behind 18) or carry in a batch
- PR 318: coordinator: close after 381
- PR 322: rebase on main acaf5f2 (behind 17) or carry in a batch
- PR 325: rebase on main acaf5f2 (behind 17) or carry in a batch
- PR 326: close C-729 conditions; DIRTY: resolve conflicts / rebase; close open conditions, then delta verdict; rebase on main acaf5f2 (behind 17) or carry in a batch
- PR 327: coordinator: close
- PR 330: coordinator: close after 381; DIRTY: resolve conflicts / rebase
- PR 331: fix red CI; rebase on main acaf5f2 (behind 17) or carry in a batch
- PR 332: rebase on main acaf5f2 (behind 17) or carry in a batch
- PR 333: rebase on main acaf5f2 (behind 17) or carry in a batch
- PR 334: rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 335: rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 336: close open conditions, then delta verdict; rebase on main acaf5f2 (behind 17) or carry in a batch
- PR 337: rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 338: rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 339: close open conditions, then delta verdict; rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 341: C-1016 conditions; close open conditions, then delta verdict; rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 342: rebase on main acaf5f2 (behind 17) or carry in a batch
- PR 343: close open conditions, then delta verdict; rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 344: close open conditions, then delta verdict; rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 345: coordinator: close after 400
- PR 346: close open conditions, then delta verdict; rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 347: close open conditions, then delta verdict; rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 348: rebase on main acaf5f2 (behind 5) or carry in a batch
- PR 349: rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 351: close open conditions, then delta verdict; rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 352: fix commit identity; resolve docs/ENVIRONMENT.md conflict with 358; close open conditions, then delta verdict; rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 353: coordinator: close after 400
- PR 355: F-C847-1/-2 marked "for Don" by the builder; not found in DECISIONS-FOR-DON; close open conditions, then delta verdict; rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 356: rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 358: rebase on main acaf5f2 (behind 10) or carry in a batch
- PR 359: DIRTY: resolve conflicts / rebase; close open conditions, then delta verdict; rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 360: close open conditions, then delta verdict; rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 361: rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 362: DIRTY: resolve conflicts / rebase; close open conditions, then delta verdict; rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 363: close open conditions, then delta verdict; rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 365: close open conditions, then delta verdict; rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 366: rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 367: close open conditions, then delta verdict; rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 368: C-775 conditions; close open conditions, then delta verdict; rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 369: rebase on main acaf5f2 (behind 10) or carry in a batch
- PR 370: coordinator: close after 400
- PR 371: address C-883 FAIL findings; rebase on main acaf5f2 (behind 10) or carry in a batch
- PR 372: close open conditions, then delta verdict; rebase on main acaf5f2 (behind 10) or carry in a batch
- PR 373: close open conditions, then delta verdict; rebase on main acaf5f2 (behind 10) or carry in a batch
- PR 374: close open conditions, then delta verdict; rebase on main acaf5f2 (behind 10) or carry in a batch
- PR 375: F-C1048-2: Don confirms the live operators file before any deploy (not a merge gate); rebase on main acaf5f2 (behind 10) or carry in a batch
- PR 377: close open conditions, then delta verdict; rebase on main acaf5f2 (behind 10) or carry in a batch
- PR 378: rebase on main acaf5f2 (behind 10) or carry in a batch
- PR 379: close open conditions, then delta verdict; rebase on main acaf5f2 (behind 10) or carry in a batch
- PR 380: rebase on main acaf5f2 (behind 13) or carry in a batch
- PR 381: rebase on main acaf5f2 (behind 10) or carry in a batch
- PR 382: rebase on main acaf5f2 (behind 10) or carry in a batch
- PR 383: docs/ENVIRONMENT.md conflict with 352/381: whichever lands second refreshes; rebase on main acaf5f2 (behind 10) or carry in a batch
- PR 385: coordinator: close after 400
- PR 387: port 65a37a0..98de2c7 onto PR 400 or re-cut; rebase on main acaf5f2 (behind 17) or carry in a batch
- PR 388: rebase on main acaf5f2 (behind 5) or carry in a batch
- PR 391: coordinator: close after 400; DIRTY: resolve conflicts / rebase
- PR 395: rebase on main acaf5f2 (behind 17) or carry in a batch

## Not determined

- Whether any PASS WITH CONDITIONS conditions were closed by non-code means (PR text, rulings) on the same head: not checked condition by condition; treated as open.
- Builder GX10 claims taken from builder notes; not re-verified against ~/ff-work markers on the GX10.
- PR 336: C-695 conditions other than (b) (Don 2026-11-05: kill-switch guard "path alone") not verified closed.
- PR 400 (compose re-cut, C-1032) GX10: the PR body points to a builder note; no comms note names fe2eed3.
- PR 345 base `test/compose-resolved-bind-c512` belongs to PR 328 (merged via batch CA); the branch still exists, so 345 is not based on main.

