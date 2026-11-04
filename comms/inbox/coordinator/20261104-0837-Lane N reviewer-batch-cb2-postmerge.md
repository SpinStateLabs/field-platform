# Reviewer (read-only, post-merge): batch cb2 = MERGE 1, main acaf5f24 -> 4d0c3315 (PR 361 @7525a93, PR 366 @3436007; 8 commits)

**Verdict: PASS WITH CONDITIONS (post-merge read) on batch head `4d0c3315`** (full PR heads: 361 `7525a9364446a6eae32da44c4c7a2b35c2b8fed0`, 366 `3436007e5071a816f50c8959171ac00e774ef55a`). Tests and one README line only. No earlier file names cb2 as a batch; this is that file.

## Record checked (HIGH, from git and gh)
- 8 commits (STATUS: 8), a fast-forward, 0 nonconforming identities (Don Hagell noreply, author and committer). PRs 361 and 366 CLOSED with a pointer comment each, CI SUCCESS 7/7 on each head.
- Reviewer verdicts naming the heads: PR 361 in `...-reviewer-c43-deltas-pr349-pr352-pr358-pr361.md`; PR 366 in c799, c986, c841 (and c1004). The file-name dates are not commit dates (they run past the merge date), so ORDER of verdict before merge is not shown by names (git log dates are the reference; not compared here, MEDIUM).
- Verifier on the batch head: `20261101-0154-gx10-verifier-batch-cb2.md` names 4d0c33153131e47479a8e6145c71d2dd5ec87155 and "16 of 16 suites passed, 0 failed".

## Objections first
1. In `tools/tests/test_workflow_security_lint.py` the lint's regex lives INSIDE the test file next to its fixtures: the test is the lint. A mutant of the regex is therefore killed only by the fixtures the same file lists; there is no second source.
2. The crosswalk signer test pins that a non-text signer is named by type only; the dangerous alternative (echoing a value that may hold a secret) is what the mutants try.
3. The new lint rule treats `github[<anything but exactly one literal>]` as a dynamic key: a stricter rule than before, so it can raise findings on workflow files that were clean; the real workflow files in the repo pass (132 tests green).

## Measured (GX10 ~/ff-work/wt-cb2 at 4d0c3315, python -B, own venv)
`test_workflow_security_lint.py` 132 passed; crosswalk `test_signer_sanitise_c252.py` 103 passed. The 16-suite is the verifier's report.

## Mutants (30 rows; source restored, worktree clean)
| Behaviour | Killed | Survived |
|---|---|---|
| D1 the dynamic-key rule is case-insensitive | 4 | 0 |
| D2 spaces before the bracket are tolerated | 3 | 1 (gap: `github[ ]?[` accepts one space only; two spaces or a tab are unpinned) |
| D3 more than one literal in the brackets is dynamic | 5 | 0 |
| D4 the double-quoted branch is exactly one literal | 2 | 2 (gaps: an empty `""` key and a quote-run quantifier) |
| D5 a literal key with spaces is not dynamic | 3 | 1 (gap: `\s?` for `\s*`, one space only) |
| D6 the word boundary (`mygithub[...]` is not `github`) | 4 | 0 |
| S1 the non-text signer message names only the type | 5 | 0 |
Totals counted from the table: killed 4+3+5+2+3+4+5 = 26; survived 0+1+0+2+1+0+0 = 4; 30 rows. All 4 survivors are regex arity gaps (one whitespace versus many); the security-relevant claim S1, that no value reaches the error, has 5 kills.

## Conditions
- C1: none blocking (merged; record complete).

## Findings (non-blocking; new PR only)
- F-cb2-1 LOW: add `github  [x]`, a tab, `github[  'sha'  ]` and `github[""]` to the lint fixtures so whitespace arity and the empty literal are pinned (D2, D4, D5).
- F-cb2-2 INFO: the lint's regex has no second copy, so a weakening of it in a future edit can only be caught by its own fixture list; keep the list the single place a new bypass spelling is added first.
