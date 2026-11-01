# rebase builder: refresh of rebase/358, 348, 402 onto main 9468b184 (new branches, old ones untouched)

Main: 9468b184383ebe66e94107b76ed7fb2d89bd797a. Identity: Don Hagell <13129187+dhagell@users.noreply.github.com> on every commit I made (see flag below).

| PR | new branch | head | old branch head | commits | range-diff vs old |
|---|---|---|---|---|---|
| 358 | rebase/358-2 | dad601111129acbfeb1b7203e0edcf5e3e77090e | 673a17ce (Lane 17 PASS, GX10 B 16/16) | 4 | all 4 `=` (patch-identical) |
| 348 | rebase/348-2 | aadab00535b4dfc59e8c3ebb8dabfe4bc78f792e | b5e4214d | 8 | all 8 `=` |
| 402 | rebase/402-2 | 1e5f8392c702c53ac3677eb00b4ebbedda37e8aa | 5086c124 | 2 | all 2 `=` |

Method: `git rebase --onto 9468b184 7de2a064` from the old branch in a fresh worktree (fpb-rb-<n>-2). No conflict in any of the 14 commits: nothing was resolved by hand, no line was changed.

No-semantic-change check (run): `git diff 7de2a064 <old>` and `git diff 9468b184 <new>` have the same stat for each PR (358: 3 files +103 -10; 348: 6 files +764 -47; 402: 1 file +25 -25). Main touched docs/ENVIRONMENT.md and tools/renew_token.py since 7de2a064 but neither canary.py nor ops_console/api.py, so the source anchors in ENVIRONMENT.md are unchanged.

Tests (run, py -3, local): tools/tests/test_environment_doc.py 62 passed on each of the three heads (about 160 s); tools/tests/test_renew_token_pins_c212.py 53 passed on rebase/402-2. field-agent and ops-console suites NOT run locally (no fastapi): GX10 needed.

FLAG (identity): commit 4b5804b7 on rebase/348-2 (PR 348's own commit 457ca0b0, author "Don Hagell <dhagell@users.noreply.github.com>", no numeric id; committer is the repo identity). It is a users.noreply address, not personal, and is already on PR 348's public head. I did not rewrite it (authorship is the PR's); I only saw it after the push. Your call whether to leave it.

FLAG (402): taking 402's file whole still drops the five assertions listed in note 20261101-1315 (main's 412 version); unchanged.

## For GX10 verifiers A and B (refs to fetch from GitHub)
- Verifier A: rebase/348-2 at aadab00535b4dfc59e8c3ebb8dabfe4bc78f792e (ops-console; full 16-suite run).
- Verifier B: rebase/358-2 at dad601111129acbfeb1b7203e0edcf5e3e77090e (field-agent; full run), then rebase/402-2 at 1e5f8392c702c53ac3677eb00b4ebbedda37e8aa (tests only, light run allowed per PROTOCOL).
`git fetch https://github.com/SpinStateLabs/field-platform.git refs/heads/<branch>:refs/heads/<name>`. Old PASS and GX10 results do not carry over by themselves; Lane 17's delta verdict on rebase/358 673a17ce plus the patch-identical range-diff above is the no-semantic-change evidence. PR branches untouched.
