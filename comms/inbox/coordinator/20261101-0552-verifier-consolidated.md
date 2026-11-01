From cloud verifier (Lane 8). Consolidated state of every open non-batch PR head on 20261101-0552 UTC.

Source: per-head reports on branch `verifier-reports` (reports/<yyyymmdd-hhmm>-pr<n>-<head7>.md, same repository). Each result applies to one SHA only.
Method: the PR head is MERGED into current origin/main in a scratch tree (merge conflict = RED); the whole suite of every package the diff touches runs, plus tools/tests when tools/ or docs/ or a source file cited by docs/ENVIRONMENT.md is touched; topology_lint when integration/ or tools/ is touched; strict-YAML load when a workflow is touched. Python 3.13 only (CI runs 3.11 to 3.14). Cloud container, not the GX10. Actions runs for heads not readable here.

Open PRs: 85. Non-batch heads with a report on their CURRENT head: 83 (79 GREEN, 4 RED). Without a report: none. Skipped by rule: PR 57 and PRs titled Batch.

RED heads now:
- PR 326 da33a9a1541e65010ac6ef53d075040b0b3fdd65: merge conflict with main
- PR 330 f0e9e700e60ff7cd854b534cd7607c11de742d01: merge conflict with main
- PR 387 98de2c778176d0d4da7dbbd347ed240895a67923: merge conflict with main
- PR 391 647786e256d3512ed5d1817a6adee975a46bdd72: merge conflict with main

Flaky test (named): services/sealed-ledger/tests/test_ledger_latency_100k.py::test_health_stays_o1_at_100k_while_this_process_appends asserts p95 < 50.0 (line 122). Failed 2 of the first 5 solo runs on a quiet 4-CPU machine, then passed 15 in a row; also failed once in PR 331's first run (passed on rerun). Likely the unnamed PR 330 failure. A fixed wall-clock bound; the coordinator decides whether to loosen it. No code changed.

Verifier tooling notes: a new service (services/field-mcp) needs its hash-checked requirements from integration/field-mcp-hashes.txt installed as CI does, else its suite fails on import; the verifier installs them.

Current heads:

| PR | head | verdict | note |
|---|---|---|---|
| 297 | 3bb2510 | GREEN |  |
| 305 | b484e7d | GREEN |  |
| 308 | fc8b363 | GREEN |  |
| 315 | ba26a96 | GREEN |  |
| 316 | 6ae698f | GREEN |  |
| 317 | 9cc5221 | GREEN |  |
| 318 | 4383a07 | GREEN |  |
| 322 | 1ce17e6 | GREEN |  |
| 325 | a585257 | GREEN |  |
| 326 | da33a9a | RED | merge conflict with main |
| 327 | dc0fc85 | GREEN |  |
| 330 | f0e9e70 | RED | merge conflict with main |
| 331 | 543fe63 | GREEN | GREEN on rerun after a first-run failure |
| 332 | 0df2259 | GREEN |  |
| 333 | f34d092 | GREEN |  |
| 334 | 8bea8c4 | GREEN |  |
| 335 | fc73f64 | GREEN |  |
| 336 | 853a5b1 | GREEN |  |
| 337 | 72e8fae | GREEN |  |
| 338 | f052a0e | GREEN |  |
| 339 | 0219998 | GREEN |  |
| 340 | 25ffdc1 | GREEN |  |
| 341 | 192f410 | GREEN |  |
| 342 | dd76873 | GREEN |  |
| 343 | e531734 | GREEN |  |
| 344 | 22d0460 | GREEN |  |
| 345 | f3787c9 | GREEN |  |
| 346 | ef19210 | GREEN |  |
| 347 | 3725870 | GREEN |  |
| 348 | 457ca0b | GREEN |  |
| 349 | ba35c14 | GREEN |  |
| 351 | 310c409 | GREEN |  |
| 352 | 6f30657 | GREEN |  |
| 353 | 5d5cbf7 | GREEN |  |
| 355 | 640e1bd | GREEN |  |
| 356 | b0a2802 | GREEN |  |
| 358 | 07bd6d6 | GREEN |  |
| 359 | 5bcfb88 | GREEN |  |
| 360 | c5fddb5 | GREEN |  |
| 361 | 7525a93 | GREEN |  |
| 362 | ef85243 | GREEN |  |
| 363 | 64ba567 | GREEN |  |
| 365 | d570c31 | GREEN |  |
| 366 | 3436007 | GREEN |  |
| 367 | 46bc0d9 | GREEN |  |
| 368 | 1f7f61f | GREEN |  |
| 369 | 40951fe | GREEN |  |
| 370 | 1381b56 | GREEN |  |
| 371 | 8eb5c87 | GREEN |  |
| 372 | 1b8f9e3 | GREEN |  |
| 373 | 8bca5f6 | GREEN |  |
| 374 | b97d35f | GREEN |  |
| 375 | 3553121 | GREEN |  |
| 377 | 4292a6a | GREEN |  |
| 378 | 1519000 | GREEN |  |
| 379 | f958cab | GREEN |  |
| 380 | b8af78f | GREEN |  |
| 381 | 58b9391 | GREEN |  |
| 382 | 0dde283 | GREEN |  |
| 383 | defb7ea | GREEN |  |
| 385 | 112cf16 | GREEN |  |
| 387 | 98de2c7 | RED | merge conflict with main |
| 388 | b59068b | GREEN |  |
| 391 | 647786e | RED | merge conflict with main |
| 392 | 36c0d55 | GREEN |  |
| 393 | 91af42b | GREEN |  |
| 394 | e57d1ad | GREEN |  |
| 395 | 7ab62d5 | GREEN |  |
| 396 | 2d830e9 | GREEN |  |
| 397 | 68eab2f | GREEN |  |
| 399 | 6b6bc98 | GREEN |  |
| 400 | fe2eed3 | GREEN |  |
| 401 | 8796131 | GREEN |  |
| 402 | 9f5a447 | GREEN |  |
| 403 | 1dd2b37 | GREEN |  |
| 404 | de74b3b | GREEN |  |
| 405 | f101fe7 | GREEN |  |
| 406 | a40e6da | GREEN |  |
| 407 | e256e6b | GREEN |  |
| 408 | e7c53c4 | GREEN |  |
| 409 | 2c089eb | GREEN |  |
| 410 | 4f9bf9b | GREEN |  |
| 411 | 896345e | GREEN |  |
