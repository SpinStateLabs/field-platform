# Review PR 420 @ e01094d187b08c94ef833da415596a816cd02b7f (B-14, renew_token signing pins) - reviewer ssl-ff-reviewer-3

**VERDICT: BLOCK on head e01094d1, as a branch. The test content passes (rebuild it clean). UNVERIFIED (cloud, no GX10).**

## Blocking findings (HIGH, measured)
- F-R420-1 BLOCK: the head has NO merge base with current origin/main (97dcfec1; `git merge-base` fails). `git log origin/main..pr420` lists 436 commits; `git diff origin/main pr420` is 160 files, +884 -10800. The branch is built on the history that main had before it was rewritten, so a fast-forward or merge is impossible and a merge-commit would re-import 436 old commits.
- F-R420-2 BLOCK: of those 436 commits, 207 have an author or committer identity that is not the Don Hagell numeric noreply (counts by `git log --format`: 229 correct; 50 correct author but committer GitHub; 37 and 114 and 2 and 2 carry a personal address or an empty email; 1 carries a tool address; 1 blank-author). The repository is public; the PROTOCOL commit-identity rule forbids this. Values not printed here.
- The branch's own work is 3 commits (c7e1c889, 1f462509, e01094d1) adding ONE file, `tools/tests/test_renew_token_signing_pins_b14.py` (258 lines; `git diff e01094d1~3 e01094d1`, 1 file changed). Those three carry the correct noreply identity.

## Test content, measured on a clean copy (main 97dcfec1 + that one file, scratch only)
- Baseline: 16 passed on current main (`PYTHONPATH=packages/field-core/src`). Not a baseline failure.
- Mutants of `tools/renew_token.py` (add_repo_field_core, caller_signer, ledger):
| Behaviour (from the file's own list) | Rows | Killed | Survived |
|---|---|---|---|
| repo-path fallback (A08, A09, A10, A10b, A11, A12, A13, A27) | 8 | 8 | 0 |
| signer loaded once (A01, A01b, A34) | 3 | 3 | 0 |
| dropped appends count past one (A25, A25b) | 2 | 2 | 0 |
| no key text in the unavailable line (A15, A15b) | 2 | 2 | 0 |
| blank variables count as unset (A32, A32b, A33) | 3 | 3 | 0 |
Totals counted from the table: 8+3+2+2+3 = 18 rows; killed 18; survived 0; anchor failures 0.

## Recommendation (coordinator's call)
Release this head. Rebuild as a new branch on current main with `git cherry-pick c7e1c889 1f462509 e01094d1` (or just that file), under the noreply identity, as a new draft PR; it needs a fresh independent review on that head, though the mutant result above should carry over (same file, tests pass on main). Do not push to PR 420's head. I also note `tools/renew_token.py` on this head differs from main (5 insertions, 22 deletions vs main), so the original PR's claims about it do not describe main.

## Objections
Reviewing the old head at face value would have certified a branch that cannot be merged; the mutant pass above applies only to the rebuilt file on main, not to PR 420's head.
