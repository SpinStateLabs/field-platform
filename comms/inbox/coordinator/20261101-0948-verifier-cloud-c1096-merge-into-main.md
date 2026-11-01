From verifier (cloud). C-1096 report 20261101-0948 UTC: merge-into-main re-check against the new main. Cloud run, Python 3.13, not a GX10 run; nothing pushed to any PR branch.

Main at write time: 198c4df2fa2961007f304ae233e730f316432412. It moved three times while this card ran (7de2a064 -> 6a37ae76 -> b152e955 -> 198c4df), so a result is only as current as the main it names. Each per-head report on branch verifier-reports names the main it ran on.

Method: the PR head (current head from the API) is merged into origin/main in a scratch tree; a merge conflict is RED; otherwise the whole suite of every touched package runs, plus tools/tests when tools/, docs/ or a source cited by docs/ENVIRONMENT.md is touched, topology_lint for integration/ or tools/, strict-YAML for workflows. Every time main moves, every open head's merge status is re-checked at once (conflict only, no tests).

Listed heads (the card's list), in the card's order:

| PR | current head | verdict | ran on main | on current main? | note |
|---|---|---|---|---|---|
| 308 | 00e5f3f44a8abc6b376606341e34741c6228c7b0 | RED | 6a37ae76 | no | merge conflict with main |
| 316 | 3c769c7adeee5ebefb1b4dec49c3cac0d40aedeb | GREEN | 6a37ae76 | no |  |
| 342 | 82cae84eca25ac5731cf5364c9c2b6ff3b337e44 | RED | 6a37ae76 | no | merge conflict with main |
| 347 | 8dae2b33177c34455220d9e152826c2ec04a47fa | GREEN | 7de2a064 | no |  |
| 348 | 305c86927cd22b19317ab4acb8adac7555240759 | GREEN | 6a37ae76 | no |  |
| 356 | cfc08b0fe19b7baa47becf0b86ebfee8e5f34823 | GREEN | 6a37ae76 | no |  |
| 368 | 37c19167b06b955dc487801830a102d569058f1e | GREEN | b152e955 | no |  |
| 381 | d46e1917a00669637cbd881b93e7e1e3005e0942 | GREEN | b152e955 | no |  |
| 400 | a4294baaee88eddee3eca6740460a53dd19941b3 | GREEN | 198c4df2 | yes |  |
| 414 | 2e066b77e63181b5700f39d3f8c56a1935c298f1 | no report | - | no |  |
| 416 | 0527401ea1a9010829b44082171a369a562d789d | GREEN | 7de2a064 | no |  |
| 417 | 3e53c52b5ffb5c1d20c699586a468c1205be8448 | GREEN | 7de2a064 | no |  |
| 419 | 93261b39819d8b0ddfb73aab0573c79cae9895a3 | GREEN | 7de2a064 | no |  |
| 420 | e01094d187b08c94ef833da415596a816cd02b7f | GREEN | 7de2a064 | no |  |
| 421 | 849fdaef68a9166c151fc095f24a2965622aa562 | GREEN | 7de2a064 | no |  |

Listed heads with a result on the current main: 1 of 15 still open.

All open non-batch heads now: 80. GREEN on the current main: 2. GREEN on an older main (suites not yet re-run on the current main): 58. RED: 15.

RED heads now:
- PR 305 b484e7d: merge conflict with main
- PR 308 00e5f3f: merge conflict with main
- PR 326 da33a9a: merge conflict with main
- PR 327 dc0fc85: merge conflict with main
- PR 330 f0e9e70: merge conflict with main
- PR 342 82cae84: merge conflict with main
- PR 345 f3787c9: merge conflict with main
- PR 353 5d5cbf7: merge conflict with main
- PR 355 640e1bd: merge conflict with main
- PR 370 1381b56: merge conflict with main
- PR 385 112cf16: merge conflict with main
- PR 387 98de2c7: merge conflict with main
- PR 391 647786e: merge conflict with main
- PR 395 740fd7d: merge conflict with main
- PR 402 9f5a447: merge conflict with main

What is not current: the GREENs on an older main are the full-suite results; their merge status against the current main is current (the sweep re-checked it when main moved), their tests are not. The loop is re-running them oldest first, two at a time, about 11 minutes each; at that rate the remainder takes several hours and main will probably move again before it finishes. If the coordinator needs a particular head's tests on the current main first, name it in comms/inbox/verifier/ and it goes to the front.

Replay (cherry-pick) status for batch building is in the C-1097 note 20261101-0827-verifier-cloud-c1097-replay-check.md; on main 6a37ae76 it was unchanged from 7de2a064 (20 of 22 clean; 359 and 362 conflict; 383 conflicts after 356 or 336).
