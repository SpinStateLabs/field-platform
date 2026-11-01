From verifier (cloud). C-1097 replay check, main 7de2a064be460689b85d2957fde8fdd3478687fb (7de2a064). Cloud run, scratch tree, nothing pushed, no PR branch touched.

Method: for each head (current head from the API at run time) the PR's non-merge commits (`git rev-list --reverse --no-merges origin/main..<head>`) are cherry-picked one by one onto main, the way batches are built. A commit already on main as an equivalent patch is skipped (none occurred). Result is CLEAN, or the first conflicting commit and file. 'merge commits' counts merge commits inside origin/main..head.

RESULT: 20 of 22 heads replay CLEAN. Two do not, and they are exactly the two heads that contain a merge commit.

| PR | head | non-merge commits | merge commits in range | replay onto main |
|---|---|---|---|---|
| 316 | 3c769c7 | 3 | 0 | CLEAN |
| 322 | 1ce17e6 | 6 | 0 | CLEAN |
| 336 | 853a5b1 | 13 | 0 | CLEAN |
| 344 | 22d0460 | 4 | 0 | CLEAN |
| 349 | ba35c14 | 4 | 0 | CLEAN |
| 356 | cfc08b0 | 11 | 0 | CLEAN |
| 359 | 5bcfb88 | 7 | 1 | CONFLICT at commit 77b689c, file docs/ENVIRONMENT.md |
| 363 | 64ba567 | 5 | 0 | CLEAN |
| 373 | 8bca5f6 | 4 | 0 | CLEAN |
| 375 | 3553121 | 8 | 0 | CLEAN |
| 382 | 0dde283 | 3 | 0 | CLEAN |
| 383 | defb7ea | 2 | 0 | CLEAN |
| 388 | b59068b | 7 | 0 | CLEAN |
| 392 | 36c0d55 | 1 | 0 | CLEAN |
| 394 | e57d1ad | 6 | 0 | CLEAN |
| 401 | 8796131 | 1 | 0 | CLEAN |
| 403 | 1dd2b37 | 1 | 0 | CLEAN |
| 404 | de74b3b | 1 | 0 | CLEAN |
| 362 | ef85243 | 3 | 1 | CONFLICT at commit 8a48d29, file services/sealed-ledger/tests/test_operator_observer_r2.py |
| 406 | a40e6da | 1 | 0 | CLEAN |
| 407 | e256e6b | 2 | 0 | CLEAN |
| 420 | e01094d | 3 | 0 | CLEAN |

Same two heads merge CLEAN as a whole into main in the cloud gate (359 and 362 are GREEN there), as with PR 358: a head that is itself a merge of main carries the resolution in its merge commit, and replaying its commits loses it. A batch that cherry-picks 359 or 362 needs the conflict resolved by hand (359: docs/ENVIRONMENT.md at 77b689c; 362: services/sealed-ledger/tests/test_operator_observer_r2.py at 8a48d29). A squash or merge of the head does not.

docs/ENVIRONMENT.md group (322, 356, 359, 336, 344, 383), every ordered pair replayed on a fresh main (earlier PR first, then the later one):

| pair | result |
|---|---|
| 322+356 | CLEAN |
| 322+359 | CONFLICT at 77b689c, file docs/ENVIRONMENT.md |
| 322+336 | CLEAN |
| 322+344 | CLEAN |
| 322+383 | CLEAN |
| 356+359 | CONFLICT at 77b689c, file docs/ENVIRONMENT.md |
| 356+336 | CLEAN |
| 356+344 | CLEAN |
| 356+383 | CONFLICT at 2b22bac, file docs/ENVIRONMENT.md |
| 359+336 | the first PR (359) already conflicts alone at 77b689c |
| 359+344 | the first PR (359) already conflicts alone at 77b689c |
| 359+383 | the first PR (359) already conflicts alone at 77b689c |
| 336+344 | CLEAN |
| 336+383 | CONFLICT at 2b22bac, file docs/ENVIRONMENT.md |
| 344+383 | CLEAN |

Pairs that are clean: 322+356, 322+336, 322+344, 322+383, 356+336, 356+344, 336+344 (agrees with C-1074), 344+383. Pairs that conflict for a reason of their own: 356+383 and 336+383 (docs/ENVIRONMENT.md at 2b22bac, 383's first commit). Every pair with 359 conflicts because 359 conflicts alone.

Cumulative chain in the v2 stage-3 order (322, 356, 359, 336, 344, 383), each PR replayed on top of the previous ones, a conflicting PR skipped so the rest can be seen:
- 322: CLEAN
- 356: CLEAN
- 359: CONFLICT at 77b689c, file docs/ENVIRONMENT.md
- 336: CLEAN
- 344: CLEAN
- 383: CONFLICT at 2b22bac, file docs/ENVIRONMENT.md

So in the table's order the chain breaks at 359 (alone) and at 383 (after 356 and 336). Clean subset without 359 and 383: 322, 356, 336, 344 replay clean in that order, and tools/tests/test_environment_doc.py passes on main plus those four (48 passed). 383 conflicts only because 356 and 336 shift the same ENVIRONMENT.md rows; it is clean after 322 or after 344 alone, so 383 last needs its ENVIRONMENT.md line numbers re-set after 356 and 336, as the rebase builder did for 358.

Not run: the test suites on any replayed tree except test_environment_doc.py on the clean subset; the full chain with 359 and 383 resolved by hand; heads outside the list. Python 3.13 only; not a GX10 run.
