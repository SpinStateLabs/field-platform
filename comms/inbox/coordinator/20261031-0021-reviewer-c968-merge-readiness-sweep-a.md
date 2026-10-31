VERDICT: INFORMATION (no verdict on code) on main acaf5f241f00754442c7adbbb0290769dbfe52c5

Reviewer Lane 15, cloud-reviewer. UNVERIFIED: no GX10, CI not read. Method: open PR list and head shas from the GitHub API (list of open PRs, drafts), each head fetched by pull ref, `git merge-tree --write-tree` of each head against origin/main acaf5f2 (fetched now); "files" = files changed against the PR's own merge base. The `gh` CLI is not available in this session, so mergeable state was computed, not read.

## Objections first
1. "clean" means no textual conflict with main; it says nothing about tests passing on the merged state. Two PRs that touch different files can still break each other; no combined run was done (HIGH).
2. Main moved: acaf5f2 carries batch BZ2's five commits (patch-equal to PR 389 and PR 386). Every PR stacked on the same bind-source commit now conflicts with main (HIGH, run).
3. File overlap below is computed against each PR's own base, so PRs with an old base (BZ, BZ2, the compose stack) show overlaps that vanish once they are rebased onto main; read overlaps with 386, 389 and the compose stack as stale.

## Sweep A: open PRs 335 to 361 (24 open; 350, 354, 357 are not open)
| PR | head | merge vs main | files | note |
|---|---|---|---|---|
| 335 | fc73f64 | clean | 1 |  |
| 336 | 08463bd | clean | 7 |  |
| 337 | 72e8fae | clean | 1 |  |
| 338 | f052a0e | clean | 2 |  |
| 339 | 0219998 | clean | 2 |  |
| 340 | 25ffdc1 | clean | 1 |  |
| 341 | 67fefb5 | clean | 3 |  |
| 342 | 697b8ec | clean | 28 | 28 files; touches todo.md, compose gb10, ci.yml |
| 343 | e531734 | clean | 2 |  |
| 344 | 627532e | clean | 5 |  |
| 345 | f3787c9 | CONFLICT: compose_bind_rules.py, test_compose_static_pins.py | 4 | stale base vs main (bind-source commit is on main) |
| 346 | ef19210 | clean | 4 | touches ci.yml |
| 347 | 10dfdef | clean | 2 |  |
| 348 | 7d332d1 | CONFLICT: ENVIRONMENT.md | 5 | ENVIRONMENT.md cell conflict |
| 349 | ba35c14 | clean | 5 |  |
| 351 | 310c409 | clean | 2 |  |
| 352 | 6f30657 | clean | 3 |  |
| 353 | 5d5cbf7 | CONFLICT: compose_bind_rules.py, compose_resolved_check.py, test_compose_resolved_bind_c512.py, test_compose_static_pins.py | 5 | same |
| 355 | 640e1bd | clean | 2 |  |
| 356 | 3361e01 | clean | 12 |  |
| 358 | 07bd6d6 | clean | 3 |  |
| 359 | 8948389 | CONFLICT: ENVIRONMENT.md | 6 | ENVIRONMENT.md cell conflict |
| 360 | c5fddb5 | clean | 2 |  |
| 361 | 7525a93 | clean | 1 |  |

Conflicts with main in this range: 345, 348, 353, 359.
Heads moved since the head each reviewer card named: none checked here beyond the sha7 column (the column marks MOVED when the sha differs from the API head at the time of the sweep: none).

## File-overlapping pairs in A (own-base diff)
- docs/ENVIRONMENT.md: 336, 348, 352, 356, 358, 359 (every pair of these; first-read table cells): 348 and 359 already conflict with main; 352+358 conflict with each other (C-43, C-965).
- 336+344: tools/tests/http_env_proxy_allowlist.txt. 338+342: docs/IMPLEMENTATION.md. 341+352: force-gateway api.py (docstrings vs code lines; clean per my probes). 342+346: ci.yml. 342+356: token-renewal runbook. 345+353: the four compose files (the stack; 353 includes the shared rules). 358+359: canary.py and ENVIRONMENT.md.

## Batch hints
Safe-looking singletons (clean, no pair overlap): 335, 337, 339, 340, 341 (with 352 lines), 343, 347, 349, 351, 355, 360, 361. Docs-only: 335, 337, 338, 340, 341, 351. PRs touching tasks/todo.md, compose or ci.yml in A: 342 (all three), 345, 353 (compose), 346 (ci.yml).
