# field-platform merge-readiness table, v2

- Repo: SpinStateLabs/field-platform (public). Read-only build: nothing merged, pushed or commented.
- main head: `acaf5f241f00754442c7adbbb0290769dbfe52c5` (unchanged since v1).
- Data time: PR list via `gh pr list` at 2026-11-01 06:12Z (heads, CI rollup, base); first read 05:56Z. comms read up to `1fde42c4bd8e3df98ebbaac54067ad003b567999` (06:11Z). comms moves every few minutes; anything after 06:12Z is not in this table.
- Open PRs: 85.
- File citations: every report is `comms/inbox/coordinator/<file>` on origin/comms. "V" = the verifier (cloud) note `20261101-0552-verifier-consolidated.md` (cloud run, Python 3.13, head merged into origin/main acaf5f2 in a scratch tree; NOT a GX10 run). Its 06:05 repeat (`20261101-0605-verifier-cloud-consolidated.md`) has the same results.
- Coordinator input (06:2xZ message, not a comms file): PRs 361 and 366 are already in batch branch `batch/2026-11-01-cb2` (head 4d0c3315); PR 358 conflicts with main in docs/ENVIRONMENT.md. The 358 claim CONTRADICTS V (GREEN on 07bd6d6); not resolved here, 358 held as NOT READY.

## Rules applied (state them so they can be audited)

1. Reviewer gate: PASS on the exact current head, by a lane that is not the author lane. A PASS WITH CONDITIONS (PWC) counts only when every condition the reviewer marked blocking is closed on that head; conditions the reviewer itself labelled non-blocking, optional, or "before deploy / before writes are enabled" are listed but do not gate merge. Where one reviewer PASSes and another PWC with an open condition on the same head, the row is READY with a FLAG.
2. GX10 gate: a gx10-verifier report or a builder note stating 16 suites, 0 failed on the exact head; docs-only PRs may use a light run labelled "light run, docs only". Reviewer "merged state" runs and partial suites do not count.
3. CI: `statusCheckRollup` at 06:12Z, all checks SUCCESS.
4. Merge-into-main: V only. Cloud, not GX10.
5. Held / superseded / stacked per the brief and tasks/DECISIONS-FOR-DON.md (last changed 2026-10-31T01:01Z; only PR 57 is held there).
6. NOT applied: PROTOCOL.md line 8 also says the head must be "rebased on current main". No READY head was checked for containing acaf5f2 (the check timed out). V shows each merges clean, but strictly PROTOCOL wants a rebase or a patch-id batch (as batch CA / cb2). Coordinator decides.
7. "Design" lane verdicts (C-614 Lane 10, C-694, C-711) counted as reviewer verdicts, as v1 did.

## Counts per class (primary reason)

| Class | Count | PRs |
|---|---|---|
| READY | 26 | 316, 317, 322, 331, 332, 333, 336, 337, 338, 344, 347, 349, 356, 359, 363, 373, 375, 382, 383, 388, 392, 394, 401, 402, 403, 404 |
| READY, IN BATCH cb2 (do not merge alone) | 2 | 361, 366 |
| HOLD (Don) | 1 | 57 |
| SUPERSEDED / DUPLICATE | 10 | 305, 308, 315, 318, 327, 330, 340, 345, 353, 398 |
| STACKED on unmerged base | 5 | 370, 385, 387, 391, 409 |
| CONFLICT with main | 2 | 326, 358 (330, 387, 391 also RED, counted above) |
| VERDICT FAIL | 3 | 371, 400, 408 |
| STALE HEAD (moved 06:10Z, CI pending) | 4 | 395, 397, 399, 405 |
| CI RED | 3 | 297, 410, 411 |
| NO GX10 (only gap) | 13 | 325, 334, 335, 341, 348, 362, 377, 378, 381, 393, 396, 406, 407 |
| CONDITIONS OPEN | 16 | 339, 342, 343, 346, 351, 352, 355, 360, 365, 367, 368, 369, 372, 374, 379, 380 |
| Total | 85 | |

## Table (READY first, then by PR)

| PR | head | CI | verifier (cloud) merge-into-main [V] | reviewer verdict + report | GX10 + report | state |
|---|---|---|---|---|---|---|
| 316 | 6ae698f | 7/7 | GREEN | C-567 PASS, 1 non-blocking (Lane 4) `20261106-0900-reviewer-c567-c458-pr316-console-csp.md`; C-973 PWC, conditions are declared limits `20261031-0026-reviewer-c973-pr317-pr316-gx10-needs.md` | 16/0 `20261031-2311-gx10-verifier-pr316.md` | READY |
| 317 | 9cc5221 | 7/7 | GREEN | C-973 PASS (Lane 15) `20261031-0026-reviewer-c973-...`; C-711 PASS `20261105-0000-design-c711-pr317-rate-rounding.md`; C-614 PASS `20261104-0200-design-c614-pr332-pr317-deltas.md` | 16/0 `20261031-2325-gx10-verifier-pr317.md` | READY |
| 322 | 1ce17e6 | 7/7 | GREEN | C-993 PASS (Lane 15) `20261031-0041-reviewer-c993-pr322-recheck.md` | 16/0 `20261101-0105-gx10-verifier-pr322.md` | READY (land before 395) |
| 331 | 543fe63 | 7/7 | GREEN (passed on rerun; flaky latency test named in V) | C-1056 PASS (Lane 7) `20261031-1830-reviewer-c1056.md` | 16/0 on 543fe639 (builder Lane 12) `20261031-1700-builder-lane12-c1060-pr297-pr331-ci.md` | READY |
| 332 | 0df2259 | 7/7 | GREEN | C-614 PASS (Lane 10) `20261104-0200-design-c614-...` | 16/0 `20261031-2339-gx10-verifier-pr332.md` | READY |
| 333 | f34d092 | 7/7 | GREEN | C-1056 PASS (Lane 7) `20261031-1830-reviewer-c1056.md` | 16/0 on f34d092d (builder Lane 2) `20261105-0100-builder-lane2-c715-c725.md` | READY |
| 336 | 853a5b1 | 7/7 | GREEN | Q-08 PASS (Lane 15) `20261101-0320-reviewer-q08-pr336-kill-switch-self-route-guard.md`; C-1074 PWC, C1 non-blocking (record Don's F-C525-2 ruling in repo) `20261101-0330-reviewer-c1074.md` | 16/0 on 853a5b1e (builder Lane 12) `20261031-1900-builder-lane12-c1061-conditions.md`, `20261031-2000-builder-lane12-c1064-conditions-and-gx10.md` | READY |
| 337 | 72e8fae | 7/7 | GREEN | C-694 PASS `20261104-1500-design-c694-pr337-pr338-pr340-pr341-docs-deltas.md` | light run, docs only, 2/0 `20261101-0032-gx10-verifier-pr337.md` | READY |
| 338 | f052a0e | 7/7 | GREEN | C-694 PASS (same file) | 16/0 `20261031-2354-gx10-verifier-pr338.md` | READY |
| 344 | 22d0460 | 7/7 | GREEN | Q-09 PASS (Lane 15) `20261101-0321-reviewer-q09-pr344-lifecycle-cli-proxy-env.md`; C-1074 PWC, nothing blocks this PR `20261101-0330-reviewer-c1074.md` | 16/0 on 22d04601 (builder Lane 12) `20261031-2000-builder-lane12-c1064-...` | READY. FLAG: Q-09 F-Q09-1 (private-CA regression) "a ruling for Don", not in DECISIONS-FOR-DON; CONFLICTS with PR 381 in lifecycle_manager/cli.py (Q-21) |
| 347 | 3725870 | 7/7 | GREEN | Q-10 PASS (Lane 15) `20261101-0322-reviewer-q10-pr347-edge-block-checker-shapes.md`; C-1075 PWC, all non-blocking `20261101-0310-reviewer-c1075-prs-347-362-407.md` | 16/0 (builder Lane 11) `20261031-1445-builder-lane11-c1062-c1063-pr347-pr363.md` | READY |
| 349 | ba35c14 | 7/7 | GREEN | C-43 PASS (Lane 4) `20261106-1800-reviewer-c43-deltas-pr349-pr352-pr358-pr361.md` | 16/0 `20261101-0008-gx10-verifier-pr349.md` | READY |
| 356 | b0a2802 | 7/7 | GREEN | Q-28 PASS (Lane 15) `20261101-0520-reviewer-q28-pr356-host-predicate-delta-c1047.md` | 16/0 run c1071a (builder Lane 11) `20261101-0445-builder-lane11-c1071-prs-356-375-402.md` | READY |
| 359 | 5bcfb88 | 7/7 | GREEN | Lane 8 PWC `20261101-0400-reviewer-lane8-q11-pr359-5bcfb881.md`: blocking C1 = CI green + full GX10 on 5bcfb881, both now met; C2/C3 non-blocking | 16/0 on 5bcfb881 (builder Lane 12) `20261101-1300-builder-lane12-pr359-gx10.md` | READY (CI read 06:12Z) |
| 363 | 64ba567 | 7/7 | GREEN | C-1076 PASS (Lane 15) `20261101-0335-reviewer-c1076-prs-363-377-393-408.md` | 16/0 run c1062b (builder Lane 11) `20261031-1445-builder-lane11-...` | READY |
| 373 | 8bca5f6 | 7/7 | GREEN | C-1074 PASS (Lane 7) `20261101-0330-reviewer-c1074.md` | 16/0 on 8bca5f65 (builder Lane 12) `20261031-2000-builder-lane12-c1064-...` | READY |
| 375 | 3553121 | 7/7 | GREEN | Q-29 PASS (Lane 15) `20261101-0535-reviewer-q29-pr375-verifier-prefix-delta.md` | 16/0 run c1071b (builder Lane 11) `20261101-0445-builder-lane11-c1071-...` | READY. FLAG: F-C1048-2 Don confirms the estate operators file before DEPLOY (not merge); conflicts with PR 355 in a test file (Q-29) |
| 382 | 0dde283 | 7/7 | GREEN | C-43 PASS (Lane 4) `20261108-0300-reviewer-c43-deltas-pr369-pr381-pr391-pr382.md` | light run, docs only, 2/0 `20261101-0041-gx10-verifier-pr382.md` | READY |
| 383 | defb7ea | 7/7 | GREEN | C-43 PASS (Lane 4) `20261106-1600-reviewer-c43-pr383-delta-pr388.md`; C-942 confirms `20261107-0300-reviewer-c939-c940-c942-pr391-pr388-pr383.md` | 16/0 `20261101-0022-gx10-verifier-pr383.md` | READY (touches 14 services: merge last) |
| 388 | b59068b | 7/7 | GREEN | C-1055 PASS (Lane 14) `20261031-1752-reviewer-c1055-tests-prs-387-388-404-406-407.md` | 16/0 on b59068b4 (builder Lane 12) `20261109-0200-builder-lane12-pr388-gx10.md` | READY |
| 392 | 36c0d55 | 7/7 | GREEN | C-43 PASS (Lane 4) `20261107-0700-reviewer-c43-deltas-pr381-pr325-pr388-pr392.md` | light run, docs only, 2/0 `20261101-0051-gx10-verifier-pr392.md` | READY. FLAG: C-989 PWC on the same head, condition (STATE.md soak lines, coordinator-owned) open `20261031-0041-reviewer-c989-pr392-c0-cadence.md` |
| 394 | e57d1ad | 7/7 | GREEN | Q-25 PASS (Lane 15) `20261101-0505-reviewer-q25-pr394-validation-422-delta-c1034.md` | green full run on e57d1ada (builder Lane 12) `20261101-1200-builder-lane12-c1066-c1073.md` | READY |
| 401 | 8796131 | 7/7 | GREEN | C-1054 PASS (Lane 7) `20261031-1816-reviewer-c1054.md` | 16/0 (builder Lane 13) `20261031-1130-builder-lane13-c1046.md` | READY |
| 402 | 9f5a447 | 7/7 | GREEN | Q-30 PASS (Lane 15) `20261101-0545-reviewer-q30-pr402-renew-token-pins.md` | 16/0 run c1071c (builder Lane 11) `20261101-0445-builder-lane11-c1071-...` | READY |
| 403 | 1dd2b37 | 7/7 | GREEN | C-1054 PASS (Lane 7) `20261031-1816-reviewer-c1054.md` | 16/0 (builder Lane 11) `20261109-1055-builder-lane11-c1044.md` | READY |
| 404 | de74b3b | 7/7 | GREEN | C-1055 PASS (Lane 14) `20261031-1752-reviewer-c1055-...` | 16/0 plus retro suite (builder Lane 12) `20261031-1100-builder-lane12-c1045-pr404.md` | READY |
| 361 | 7525a93 | 7/7 | GREEN | C-43 PASS `20261106-1800-reviewer-c43-deltas-...` | 16/0 `20261101-0119-gx10-verifier-pr361.md` | READY, but carried in batch cb2 (coordinator): merge via the batch, not alone |
| 366 | 3436007 | 7/7 | GREEN | C-841 PASS, 1 non-blocking `20261105-2335-reviewer-c841-pr366-delta-signer-message.md` | 16/0 `20261101-0133-gx10-verifier-pr366.md` | READY, but carried in batch cb2 (coordinator) |
| 57 | 30ac1e1 | 7/7 | not run (skipped by rule, V) | C-843 PWC (v1) | 17/0 (v1) | NOT READY: HOLD, Don decides the merge (DECISIONS-FOR-DON); conditions open |
| 297 | 3bb2510 | 6/7 (tests 3.12 FAILURE) | GREEN | C-473 PASS `20261102-0600-reviewer-c473-pr297-lessons.md` | light run, docs only `20261101-0143-gx10-verifier-pr297.md` | NOT READY: CI red (flake not reproduced, `20261031-1700-builder-lane12-c1060-...`) |
| 305 | b484e7d | 7/7 | GREEN | PWC (v1) | none found | NOT READY: superseded (305/308 pick one) |
| 308 | fc8b363 | 7/7 | GREEN | cloud C-972 PWC (v1) | none found | NOT READY: superseded (305/308 pick one) |
| 315 | ba26a96 | 7/7 | GREEN | C-509 PWC, not recommended (v1) | partial only | NOT READY: superseded |
| 318 | 4383a07 | 7/7 | GREEN | C-710 PWC (v1) | none found | NOT READY: superseded by 381 |
| 325 | a585257 | 7/7 | GREEN | Q-20 PASS (Lane 15), C-961 conditions non-blocking `20261101-0350-reviewer-q20-pr325-removal-date-window.md` | none found on a585257 (`20261101-0246-builder-lane1-c1012.md`: not run) | NOT READY: no GX10 |
| 326 | da33a9a | 7/7 | RED (merge conflict) | C-729 PWC, cloud C-791 FAIL (v1) | none found | NOT READY: conflict; conditions open |
| 327 | dc0fc85 | 7/7 | GREEN | none on dc0fc85 (v1) | none found | NOT READY: superseded by 322 |
| 330 | f0e9e70 | none | RED (merge conflict) | C-838 PWC (v1) | none found | NOT READY: superseded by 381; conflict; no CI |
| 334 | 8bea8c4 | 7/7 | GREEN | C-1053 PWC, C1 non-blocking (Lane 14) `20261031-1743-reviewer-c1053-docs-prs-334-335-378-393-396-398.md` | none found | NOT READY: no GX10 (light run allowed) |
| 335 | fc73f64 | 7/7 | GREEN | C-1053 PASS (same file) | none found | NOT READY: no GX10 (light run allowed) |
| 339 | 0219998 | 7/7 | GREEN | cloud C-458 PWC, C1 live header check, C2 close 314: open (`20261031-1900-builder-lane12-c1061-conditions.md`) | none found | NOT READY: conditions open; no GX10 |
| 340 | 25ffdc1 | 7/7 | GREEN | C-933 PASS (v1) | partial only | NOT READY: duplicate of 398 (C-1053 F-C398-1: merge one, close the other); no GX10 |
| 341 | 192f410 | 7/7 | GREEN | Q-22 PASS (Lane 15) `20261101-0425-reviewer-q22-pr341-adr10-notes-symbols.md` | none found (`20261101-2000-builder-lane1-c1026.md`: not run) | NOT READY: no GX10 (api.py docstrings changed: full run) |
| 342 | dd76873 | 7/7 | GREEN | C-1056 PWC: moves slack, Don's C-561 rulings, re-run guard: open `20261031-1830-reviewer-c1056.md` | none found | NOT READY: conditions open (incl. Don rulings); no GX10 |
| 343 | e531734 | 7/7 | GREEN | cloud C-979 PWC open (v1; Lane 12 named out of scope) | none found | NOT READY: conditions open; no GX10 |
| 345 | f3787c9 | 7/7 | GREEN | C-640 PWC (v1) | partial only | NOT READY: superseded by 400; base test/compose-resolved-bind-c512 |
| 346 | ef19210 | 8/8 | GREEN | cloud C-868 PWC (v1) | none found | NOT READY: conditions open; no GX10 |
| 348 | 457ca0b | 7/7 | GREEN | Q-23 PASS (Lane 15) `20261101-0450-reviewer-q23-pr348-delta-c936.md` | none found (`20261101-2000-builder-lane1-c1009.md`: not run) | NOT READY: no GX10. Conflicts with 381 and 352 in docs/ENVIRONMENT.md (Q-23) |
| 351 | 310c409 | 7/7 | GREEN | cloud C-956 PWC open (v1) | full run on 310c4099 (Lane 12, v1) | NOT READY: conditions open |
| 352 | 6f30657 | 7/7 | GREEN | C-43 PWC, one open item (commit authored "Claude") (v1) | none found | NOT READY: conditions open; no GX10 |
| 353 | 5d5cbf7 | 7/7 | GREEN | C-735 PWC (v1) | 16/0 (v1) | NOT READY: superseded by 400; stacked on 345 |
| 355 | 640e1bd | 7/7 | GREEN | cloud C-1002 PWC open; F-C847 items "for Don" (v1) | 16/0 (Lane 13, v1) | NOT READY: conditions open |
| 358 | 07bd6d6 | 7/7 | GREEN per V | C-43 PASS `20261106-1800-reviewer-c43-deltas-...` | 16/0 on 07bd6d63 (Lane 13) `20261105-1500-builder-lane13-conditions-c826-c827-c829-c832-c834.md` | NOT READY: coordinator reports a docs/ENVIRONMENT.md conflict with main; contradicts V; also shares canary.py and ENVIRONMENT.md with 359 (pair not checked) |
| 360 | c5fddb5 | 7/7 | GREEN | cloud C-963 PWC open (v1) | 16/0 (Lane 13, v1) | NOT READY: conditions open |
| 362 | ef85243 | 7/7 | GREEN | C-1075 PASS (Lane 14); Q-12 PASS (Lane 15) `20261101-0345-reviewer-q12-pr362-alert-send-observer-survivors.md` | none on ef85243 (`20261110-1900-builder-lane1-c1059.md`: not run; old run on b468f79 = stale head) | NOT READY: no GX10 |
| 365 | d570c31 | 7/7 | GREEN | cloud C-891 PWC open (v1) | 16/0 (Lane 13, v1) | NOT READY: conditions open |
| 367 | 46bc0d9 | 7/7 | GREEN | cloud C-891 PWC open (v1) | 16/0 (Lane 13, v1) | NOT READY: conditions open |
| 368 | 1f7f61f | 7/7 | GREEN | C-775 PWC open (v1) | none found (reviewer "CI suites green" is not a GX10 run) | NOT READY: conditions open; no GX10 |
| 369 | 40951fe | 7/7 | GREEN | Q-24 PWC (Lane 15): F-Q24-1 pin templated trailing-control case "before a read key is issued anywhere" `20261101-0450b-reviewer-q24-pr369-read-tier-delta.md` | green full run on 40951fe6 (Lane 12) `20261101-1200-builder-lane12-c1066-c1073.md` | NOT READY: condition open (arguably deploy-only; coordinator's call) |
| 370 | 1381b56 | 7/7 | GREEN | cloud C-787 FAIL (v1) | 16/0 (v1) | NOT READY: stacked (base test/compose-resolved-conditions-c638); superseded by 400 |
| 371 | 8eb5c87 | 7/7 | GREEN | cloud C-883 FAIL (v1) | 16/0 (v1) | NOT READY: verdict FAIL |
| 372 | 1b8f9e3 | 7/7 | GREEN | C-884 PWC; C2 Don's ruling (BLOCK relay, SDK cap) open `20261031-2000-builder-lane12-c1064-...` | none found | NOT READY: conditions open (Don); no GX10 |
| 374 | b97d35f | 7/7 | GREEN | cloud C-983 PWC open; ENFORCE rule is Don's `20261031-2000-builder-lane12-c1064-...` | full run (Lane 12, v1) | NOT READY: conditions open (Don) |
| 377 | 4292a6a | 7/7 | GREEN | C-1076 PASS (Lane 15) `20261101-0335-reviewer-c1076-...` | none found (Lane 12 note mentions a light run, gives no result: `20261031-2000-builder-lane12-c1064-...`) | NOT READY: no GX10 (light run allowed) |
| 378 | 1519000 | 7/7 | GREEN | C-1053 PASS `20261031-1743-reviewer-c1053-...` | none found | NOT READY: no GX10 (light run allowed) |
| 379 | f958cab | 7/7 | GREEN | C-1006 PWC; conditions coordinator/Don `20261031-2000-builder-lane12-c1064-...` | none found | NOT READY: conditions open; no GX10 |
| 380 | b8af78f | 7/7 | GREEN | C-1057 PWC: three conditions before writes are enabled; "PR 368 is inside this head; land or close as one decision" `20261031-1830-reviewer-c1057.md` | 16/0 + field-mcp (builder Lane 16; sha not written in the note, "newest head") `20261031-1800-builder-lane16-pr380-gx10-full-set.md` | NOT READY: carries unmerged PR 368 (conditions open) |
| 381 | 58b9391 | 7/7 | GREEN | Q-21 PASS (Lane 15) `20261101-0405-reviewer-q21-pr381-delta-c1041.md` | none found (`20261101-0246-builder-lane1-c1012.md`: not run) | NOT READY: no GX10. Conflicts with 344 (cli.py) |
| 385 | 112cf16 | 7/7 | GREEN | cloud C-952 PWC (v1) | none found | NOT READY: stacked (base test/compose-pr345-conditions-c715); superseded by 400 |
| 387 | 98de2c7 | 7/7 | RED (merge conflict) | C-1055 PWC, C1 blocks merge as a branch `20261031-1752-reviewer-c1055-...` | 16/0 (v1) | NOT READY: stacked; conflict; superseded by 400 |
| 391 | 647786e | 7/7 | RED (merge conflict) | C-1030 PWC (v1) | none found | NOT READY: stacked; conflict; superseded by 400 |
| 393 | 91af42b | 7/7 | GREEN | C-1076 PASS (Lane 15) `20261101-0335-reviewer-c1076-...` | none found (`20261107-0200-builder-lane1-c466-c1053.md`: not run) | NOT READY: no GX10 (light run allowed) |
| 395 | 740fd7d | 3/7, 4 pending | none on 740fd7d (V covers 7ab62d5) | stale head: C-1058 PWC on 7ab62d5 `20261031-1820-reviewer-c1058-prs-394-395-397-399-405.md`; new head `20261101-0611-builder-lane1-c1068.md` | none found | NOT READY: stale head; stacked on 322 content (land 322 first) |
| 396 | 2d830e9 | 7/7 | GREEN | C-1053 PASS `20261031-1743-reviewer-c1053-...` | none found (`20261107-0210-builder-lane1-c760.md`) | NOT READY: no GX10 (light run allowed) |
| 397 | 4128a3a | 3/7, 4 pending | none on 4128a3a (V covers 68eab2f) | stale head: C-1058 PWC on 68eab2f; new head `20261101-0611-builder-lane1-c1068.md` | none found | NOT READY: stale head; needs public-safety reviewer |
| 398 | 3a936d9 | 7/7 | none (batch PRs skipped by V) | C-1053 PASS `20261031-1743-reviewer-c1053-...` | none found | NOT READY: duplicate of 340; no GX10; no V evidence |
| 399 | c00fd1b | 3/7, 4 pending | none on c00fd1b (V covers 6b6bc98) | stale head: C-1058 PWC on 6b6bc98; new head `20261101-2100-builder-lane1-c1067.md` | none found | NOT READY: stale head |
| 400 | fe2eed3 | 7/7 | GREEN | C-1054 FAIL (Lane 7) `20261031-1816-reviewer-c1054.md` | none found | NOT READY: verdict FAIL (F-C1054-1 regression vs main) |
| 405 | fc6b549 | 0/7, 7 pending | none on fc6b549 (V covers f101fe7) | stale head: C-1058 PWC on f101fe7; new head `20261101-0611-builder-lane1-c1068.md` | none found | NOT READY: stale head |
| 406 | a40e6da | 7/7 | GREEN | C-1055 PASS `20261031-1752-reviewer-c1055-...` | none found (`20261109-1500-builder-lane1-c1042.md`: not run) | NOT READY: no GX10 |
| 407 | e256e6b | 7/7 | GREEN | C-1075 PWC, all non-blocking `20261101-0310-reviewer-c1075-...` | none found (`20261031-1814-builder-lane1-c505-r2.md`: not run) | NOT READY: no GX10 |
| 408 | e7c53c4 | 7/7 | GREEN | C-1076 FAIL (public-safety scrub incomplete) `20261101-0335-reviewer-c1076-...` | none found | NOT READY: verdict FAIL; Don history ruling F-C408-3 |
| 409 | 2c089eb | 7/7 | GREEN | C-1074 PWC, C1 required before merge `20261101-0330-reviewer-c1074.md` | none found | NOT READY: stacked on 372 (base fix/upstream-error-field-agent-c642); C1 open |
| 410 | 4f9bf9b | 6/7 (tests 3.12 FAILURE) | GREEN | Q-26 PASS `20261101-0425b-reviewer-q26-pr410-b23-part1.md` | 16/0 (Lane 11) `20261101-0330-builder-lane11-b23-part1-pr410.md` | NOT READY: CI red |
| 411 | 896345e | 6/7 (tests 3.14 FAILURE) | GREEN | Q-31 PASS `20261101-0605-reviewer-q31-pr411-attestation-parse-verify-window.md` | 16/0 (Lane 11) `20261101-0515-builder-lane11-c1072-pr411.md` | NOT READY: CI red |

(v1) = cited from the v1 table `tasks/fp-merge-ready-table.md`, head unchanged since; no newer report found naming that head.

## Recommended merge order (READY only)

Method. PROTOCOL.md prescribes no merge command for main. It requires (line 8) "an independent reviewer PASS and a green GX10 run on the EXACT head, rebased on current main", and only the coordinator merges. Recent practice is a patch-id batch (CA; cb2 for 361/366). The `gh` lines below are the brief's form. All READY PRs are DRAFTS: `gh pr ready <n>` is needed first, or the merge is refused. After each merge, main moves and every later row's V and GX10 evidence is against an older main. Re-check any PR that shares files with one already merged.

Stage 1, no file shared with any other READY PR (any order):
```
gh pr merge 316 --squash --match-head-commit 6ae698fdbfcab597aeab145ffa5b3f0fd980947f
gh pr merge 317 --squash --match-head-commit 9cc52212607105e7e0d0ac5c81b902810f197693
gh pr merge 333 --squash --match-head-commit f34d092d19d5e0826e89b1e7b7e05ae60672a64d
gh pr merge 337 --squash --match-head-commit 72e8fae42a2a2e70df75253b4e665c862e79bb24
gh pr merge 338 --squash --match-head-commit f052a0e7de1c95b168ea19db62610667fb88be14
gh pr merge 347 --squash --match-head-commit 3725870232722506b677e8b63fa6448f0be17427
gh pr merge 363 --squash --match-head-commit 64ba5670d11ac2f3d2412ad150fa832d4e7ba64a
gh pr merge 388 --squash --match-head-commit b59068b4631e73be3508e357a2fcdfbea269c800
gh pr merge 402 --squash --match-head-commit 9f5a447ee47c4260661f23d61845beaca7a7c137
gh pr merge 403 --squash --match-head-commit 1dd2b3703a09cb53d40edca8e779dfb6bba0a419
gh pr merge 404 --squash --match-head-commit de74b3b0b50bad1a26a713d686843228dab2a4c0
```
Stage 2, pairs that share files (order as listed; a pair shown clean is cited):
```
gh pr merge 401 --squash --match-head-commit 8796131529e902a4fdfd2d8b3a54fa07299e4b69   # shares test_operator_auth_format2.py with 375; Q-29 merge-tree 375+401 clean
gh pr merge 375 --squash --match-head-commit 355312178e940a31a03d064b6d3341026b0d4837   # shares operator_auth.py with 383
gh pr merge 394 --squash --match-head-commit e57d1ada70fc6701a978a885de1087651b621fb2   # shares crosswalk api.py with 383
gh pr merge 373 --squash --match-head-commit 8bca5f6586eb75c001c094b53f78d573f7b340ae   # shares spend-governor api.py with 383
gh pr merge 349 --squash --match-head-commit ba35c14a4605e5e128f3a2ae03e5399080cbe6da   # shares delegation api.py with 383
gh pr merge 331 --squash --match-head-commit 543fe6391febe380a1c3dc790caa8f87c61ba7cc   # shares sealed-ledger README with 382
gh pr merge 332 --squash --match-head-commit 0df22595c420ca0584430ca544c0dfc0efc8f60f   # shares crosswalk README with 382 (and 366 in cb2)
gh pr merge 392 --squash --match-head-commit 36c0d55979a5e1b04421412624bf75d3e6c76760   # shares tasks/todo.md with 382
gh pr merge 382 --squash --match-head-commit 0dde283598e9359a0b8360896f2b6e649db7c85e
```
Stage 3, docs/ENVIRONMENT.md group (line-number column; re-run tools/tests/test_environment_doc.py and refresh after each):
```
gh pr merge 322 --squash --match-head-commit 1ce17e6cf0efba367d1c0f1819edb309d1b4c144
gh pr merge 356 --squash --match-head-commit b0a280290644bfe0d84e1153562ce3550ac4508c
gh pr merge 359 --squash --match-head-commit 5bcfb881cdff5a1c648d816c589776b76469aa23   # shares canary.py with 358 (not READY)
gh pr merge 336 --squash --match-head-commit 853a5b1eb81d748146d17486ac9d269fb68bea93   # shares http_env_proxy_allowlist.txt with 344; C-1074: 336+344 apply clean
gh pr merge 344 --squash --match-head-commit 22d04601cc77fb2c568cb094bf32e824d044daf2   # conflicts with 381 in cli.py (Q-21); keep both trust_env=False and follow_redirects=False
gh pr merge 383 --squash --match-head-commit defb7eaf5c705a820471b1c8904d1f3c4d44d167   # last: touches 14 services and ENVIRONMENT.md
```
Pairs within the ENVIRONMENT.md group other than 336+344 were NOT merge-checked together by any report found. 361 and 366 go in with batch cb2, not by these lines.

## One step from ready (exactly one gate missing)

- GX10 light run (docs only): 334 (plus non-blocking PWC), 335, 377, 378, 393, 396.
- GX10 full run: 325, 341, 348, 362, 381, 406, 407 (plus non-blocking PWC).
- CI green (re-run): 297 (tests 3.12), 410 (tests 3.12), 411 (tests 3.14).
- Reviewer condition closed: 369 (F-Q24-1), 351, 355 (also Don items), 360, 365, 367.

## Conflicts (RED in V, merge into main acaf5f2)

- 326 da33a9a1541e65010ac6ef53d075040b0b3fdd65
- 330 f0e9e700e60ff7cd854b534cd7607c11de742d01 (superseded by 381)
- 387 98de2c778176d0d4da7dbbd347ed240895a67923 (superseded by 400)
- 391 647786e256d3512ed5d1817a6adee975a46bdd72 (superseded by 400)
- Not in V: 358, reported by the coordinator (docs/ENVIRONMENT.md); V says GREEN on the same head. Unresolved.

## Not determined

- Whether any READY head contains main acaf5f2 (PROTOCOL "rebased on current main"); the check timed out.
- PR 380 GX10 sha: the Lane 16 note says "newest head" without the sha.
- Pairwise merges inside the ENVIRONMENT.md group (322, 336, 356, 359, 383) and 358 vs 359.
- Builder GX10 claims are taken from the notes; ~/ff-work logs were not re-read.
- Comms after 1fde42c (06:11Z) and PR heads after 06:12Z.
