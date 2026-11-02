# Lane R report: C-1100 done (three new heads on main 9addf44f), read and measured as stated

Main: 9addf44f. Old heads re-read with git ls-remote just before starting: rebase/358-2 dad60111, rebase/348-3 6671142b, rebase/402-2 1e5f8392 (unchanged, not pushed to). Identity: Don Hagell <13129187+dhagell@users.noreply.github.com> as author and committer on every commit, checked per branch (0 commits with another identity).

| PR | new branch | full head sha | commits | contains 9addf44f |
|---|---|---|---|---|
| 358 | rebase/358-c1100 | 2c2617bbe5a049a8a563a9e562d45e68f6072895 | 4 | yes |
| 348 | rebase/348-c1100 | 42b478e9c0ef9cb1142a95b0e737372787f0e243 | 8 | yes |
| 402 | rebase/402-c1100 | 45f9de756ff65706021e240f243461a38205133c | 2 | yes |

Method: `git rebase --onto 9addf44f 9468b184` from each old head in a fresh worktree. NO conflicts: no file or hunk needed a hand resolution, no line changed.
No-semantic-change evidence (run): `git range-diff 9468b184..<old head> 9addf44f..<new head>` is all `=` for every commit (4 of 4, 8 of 8, 2 of 2); the net change of each branch has the same stat as before (358: 3 files +103 -10; 348: 6 files +764 -47; 402: 1 file +25 -25). Main's change 9468b184..9addf44f is six test files only (defence-shield agent-incident-retro tests, two field-core tests, two tools tests) and none is a file or a cited source line of these three PRs, so the ENVIRONMENT.md anchors are unchanged.
Tests (local, py -3, run): tools/tests/test_environment_doc.py 62 passed on each of the three heads; tools/tests/test_renew_token_pins_c212.py 53 passed on 402. NOT run locally: the field-agent (358) and ops-console (348) suites (no fastapi); the GX10 run covers them.

Carried-over flags (unchanged): (a) rebase/402 takes PR 402's test file whole, which drops five is_guarded assertions that PR 412's version on main had (see note 20261101-1315); (b) PR 348's own commit carries its original author email in the PR itself; on this branch the identity is the repository one.

## For the next cards (C-1101/C-1102 style asks)
- Reviewer delta (no-semantic-change check) and GX10 full run are needed on each new head: the old verdicts and runs do not carry over by themselves. Prior evidence on the old heads: 358-2 Lane 17 PASS (22 of 22 mutants) and GX10 16/16; 348-3 GX10 16/16; 402-2 GX10 16/16.
- Per C-1102 the stacked batch of the three heads in order 358, 348, 402 is built by the verifier lane on 9addf44f; I have NOT built it. C-1099 (batch ma3) is Lane 13's claim; I do not hold it.
