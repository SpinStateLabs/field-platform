# rebase builder: rebase/348-3 (identity fixed) and check of PRs 347, 372, 417, 407, 414

## rebase/348-3
Branch rebase/348-3, head 6671142bc66d3cd99e4ad041c6db3a52b9e11a3f, on main 9468b184383ebe66e94107b76ed7fb2d89bd797a. Replaces rebase/348-2 (not touched, not force-pushed).
- Only commit 7 changed (was 4b5804b7): author set to Don Hagell <13129187+dhagell@users.noreply.github.com>, committer already was; author date kept. Check: `git log main..HEAD --format='%ae|%ce'` shows only the 13129187+ address on all 8 commits.
- `git range-diff 9468b184..rebase/348-2 9468b184..rebase/348-3`: commits 1-6 and 8 `=`, commit 7 `!` (author line only). `git diff rebase/348-2 rebase/348-3` is empty: the trees are identical.
- tools/tests/test_environment_doc.py: 62 passed (exit 0) on this head. ops-console suite not run locally (no fastapi): GX10 verifier A, please run rebase/348-3 at 6671142bc66d3cd99e4ad041c6db3a52b9e11a3f (full run; do not run 348-2).

## Candidates you named (heads read with git ls-remote at 15:50)
| PR | head | verdict on that head | main replay |
|---|---|---|---|
| 347 | 8dae2b33 | Lane 7 PASS (Q-57) | 9 non-merge commits, 0 merge commits, merge-tree with 9468b184 CLEAN |
| 417 | 3e53c52b | PASS WITH CONDITIONS (Q-46) | 2 commits, CLEAN |
| 407 | e256e6bc | PASS WITH CONDITIONS (Q-17) | 2 commits, CLEAN |
| 414 | 2e066b77 | PASS WITH CONDITIONS (Q-68) | 6 commits, CLEAN against main; collides with PR 421 in one ci.yml hunk, a landing-order question (Q-68 C3), not a conflict with main |
| 372 | 1b8f9e3f | the verdicts I can find (C-785, C-729) name older heads (90881a5, b069869, da33a9a), not 1b8f9e3f | not carried: no verdict on the current head |
None conflicts with main, so I carried none (a linear head with no merge commit that merges clean replays clean; I did not build the replay). I will build one on request, or when 421 lands and 414 needs its ci.yml hunk resolved.
