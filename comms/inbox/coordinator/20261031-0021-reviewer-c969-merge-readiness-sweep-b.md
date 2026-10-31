VERDICT: INFORMATION (no verdict on code) on main acaf5f241f00754442c7adbbb0290769dbfe52c5

Reviewer Lane 15, cloud-reviewer. UNVERIFIED: no GX10, CI not read. Method: open PR list and head shas from the GitHub API (list of open PRs, drafts), each head fetched by pull ref, `git merge-tree --write-tree` of each head against origin/main acaf5f2 (fetched now); "files" = files changed against the PR's own merge base. The `gh` CLI is not available in this session, so mergeable state was computed, not read.

## Objections first
1. "clean" means no textual conflict with main; it says nothing about tests passing on the merged state. Two PRs that touch different files can still break each other; no combined run was done (HIGH).
2. Main moved: acaf5f2 carries batch BZ2's five commits (patch-equal to PR 389 and PR 386). Every PR stacked on the same bind-source commit now conflicts with main (HIGH, run).
3. File overlap below is computed against each PR's own base, so PRs with an old base (BZ, BZ2, the compose stack) show overlaps that vanish once they are rebased onto main; read overlaps with 386, 389 and the compose stack as stale.

## Sweep B: open PRs 362 to 391 (27 open; 364, 376, 390 are not open)
| PR | head | merge vs main | files | note |
|---|---|---|---|---|
| 362 | b468f79 | CONFLICT: test_alerts_send_survivors_c159.py, test_operator_observer_r2.py | 2 | alerts/observer test files conflict: content already on main, rebase or close |
| 363 | 02d1159 | clean | 2 |  |
| 365 | d570c31 | clean | 3 |  |
| 366 | 3436007 | clean | 2 |  |
| 367 | 46bc0d9 | clean | 3 |  |
| 368 | 1f7f61f | clean | 24 | MCP PR 1; ci.yml, hashes |
| 369 | 57a356b | clean | 3 |  |
| 370 | 1381b56 | CONFLICT: compose_bind_rules.py, compose_resolved_check.py, test_compose_resolved_bind_c512.py, test_compose_static_pins.py | 6 | same |
| 371 | 8eb5c87 | clean | 8 |  |
| 372 | 1b8f9e3 | clean | 11 |  |
| 373 | 8c3cfb5 | clean | 2 |  |
| 374 | b97d35f | clean | 3 |  |
| 375 | 4ff09c7 | clean | 7 |  |
| 377 | dfceabc | clean | 1 |  |
| 378 | 1519000 | clean | 1 |  |
| 379 | a020c33 | clean | 2 |  |
| 380 | e17ea86 | clean | 26 | MCP PR 2 (7 tools); ci.yml |
| 381 | f083ed2 | clean | 13 |  |
| 382 | 5be16e6 | clean | 4 | todo.md |
| 383 | defb7ea | clean | 20 |  |
| 384 | ca41545 | clean | 25 | MCP PR 2 (8 tools); ci.yml |
| 385 | 112cf16 | CONFLICT: compose_bind_rules.py, compose_resolved_check.py, test_compose_resolved_bind_c512.py, test_compose_static_pins.py | 7 | same |
| 386 | ab39a0f | clean | 9 | BZ: duplicate of main (patch-equal), close |
| 387 | d4902a0 | CONFLICT: compose_bind_rules.py, compose_resolved_check.py, test_compose_resolved_bind_c512.py, test_compose_static_pins.py | 8 | same |
| 388 | 9d64ff1 | clean | 1 |  |
| 389 | f7baaab | clean | 9 | BZ2: its 5 commits are ON main (patch-equal), close |
| 391 | fae8cc0 | CONFLICT: compose_bind_rules.py, compose_resolved_check.py, test_compose_resolved_bind_c512.py, test_compose_static_pins.py | 10 | same |

Conflicts with main in this range: 362, 370, 385, 387, 391.
Moved heads: none against the sha7 column.

## Files in batch BZ2 (todo.md, compose, ci.yml)
- Already on main (BZ2 landed): tasks/todo.md soak edit, tools/compose_resolved_check.py and compose_bind_rules.py, tests, ci.yml guard, runbook soaks. PRs still carrying copies: 386 (BZ), 389 (BZ2): close both.
- Still touching tasks/todo.md: 382 (soak override rows) and 342 (public-safety paths). Touching ci.yml: 342, 346 (A), 368, 380, 384 (MCP), 386, 389. Touching compose files: the 345 to 391 stack (345, 353, 370, 385, 387, 391) and 342 (gb10 overlay).

## File-overlapping pairs in B (own-base diff)
- docs/ENVIRONMENT.md: 365, 368, 369, 371, 372, 374, 380, 381, 383, 384 (and A's 336, 348, 352, 356, 358, 359): the dominant conflict surface; each of the first group is clean with main now, so merge them one at a time and re-run test_environment_doc after each.
- MCP: 368 with 380 and 384 (24 shared files, stacked; 380 and 384 are alternatives, only one can merge).
- field-core api/operator files: 371+381 (clients.py), 371+383, 373+383, 381+383 (api.py), 375+383 (operator_auth.py): clean pairwise in merge-tree.
- Runbook v1.2-deploy-rollback.md: 375, 379, 386, 389, 391 (and 342): clean with main for 379.
- 366+382 README.md. 382+386/389 todo.md (stale).

## Merge-order notes
1. Rebase the compose stack (385, 387, 391; 345, 353, 370 first) onto acaf5f2; git drops the duplicate bind-source commit.
2. 362: its test files conflict with main; the batch containing them landed, so rebase or close.
3. MCP: 368 first, then exactly one of 380 (matches the attest ruling in the design note) or 384.
4. 351, 352, 358, 361, 349, 360, 355, 325 (A and B): clean now; ENVIRONMENT.md conflicts only 352 vs 358.
