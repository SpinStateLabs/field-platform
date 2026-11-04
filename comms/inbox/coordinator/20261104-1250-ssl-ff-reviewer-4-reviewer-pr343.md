# Reviewer report: PR 343 @ e5317342aa3288153ef6f8b7a44abba372ce10c9 (C-460, reviewer C-450 / C-627 / C-730 / C-935: the CI pip-pin scanner)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Tests only: tools/tests/test_ci_pip_pins_c23.py (+669, scanner functions and their tests live in the same file) and tools/tests/test_yaml_duplicate_keys.py (+3). Base 5808a5cd (old); 4 commits, author and committer of all 4 = Don Hagell 13129187+dhagell@users.noreply.github.com, trailers Sonnet 5.5 (HIGH). `git merge-tree --write-tree origin/main pr343` clean (HIGH). No production or workflow file changed.

## Objections first
1. Scanner and its tests are in one file written together; the file's own scope statement says it is "a text scan of shell, not a shell" and that every earlier review found another spelling: it proves the pinned spellings are refused, nothing more. Accepted as stated; the verdict is about that stated scope.
2. It guards `.github/workflows/*` of the base it was built on; workflows move (PR 414 adds a `pip install $C ... vulture` word, for example). I therefore ran the same two test files on a scratch merge with current main 97dcfec1: 256 passed (the head alone: 254), so the shipped workflows on main still satisfy it (HIGH).
3. Fail-closed false positives are documented in the file (e.g. `uv sync --frozen`, `pip config list`, an `echo` that mentions pip): a future legitimate workflow edit may fail it and need a test change, by design.

## Verified
- Baseline on the exact head (relative PYTHONPATH `tools`): tools/tests/test_ci_pip_pins_c23.py + test_yaml_duplicate_keys.py 254 passed; the c23 file alone 193 passed.
- Behaviour probes run by me (not in the PR): on the head, `pip install --find-links x -c a -c b --build-constraint c foo` is refused; `pip install --constraint=a.txt --build-constraint b.txt foo` is accepted (no findings); a step whose whole run is `${{ matrix.cmd }}` is reported.

## Mutants (mutations of the scanner functions in the test file; scratch worktree on the head; baseline 193 passed in the c23 file; kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| 1 | `\|\|` not a statement separator | 193 passed | NO |
| 2 | `&&` not a separator | 1 failed | yes |
| 3 | `#` always starts a comment | 1 failed | yes |
| 4 | line continuations not joined | 1 failed | yes |
| 5 | bare_words: quoted text transparent | 1 failed | yes |
| 6 | words: `$(` not spaced | 193 passed | NO |
| 7 | other managers (poetry, conda ...) not refused | 1 failed | yes |
| 8 | `pipx run` not refused | 1 failed | yes |
| 9 | `xargs pip` not seen | 1 failed | yes |
| 10 | uv verbs ignored | 1 failed | yes |
| 11 | `--constraint=` form ignored | 193 passed | NO |
| 12 | define arms `$C` when not standalone | 1 failed | yes |
| 13 | compound statement does not stop arming | 1 failed | yes |
| 14 | `trap` naming C does not disarm | 1 failed | yes |
| 15 | `--find-links` removed from the refused list | 193 passed | NO |
| 16 | short `-r` not refused | 1 failed | yes |
| 17 | `://` URLs not refused | 1 failed | yes |
| 18 | any statement holding `pip==` accepted as the pin | 1 failed | yes |
| 19 | inline constraints need no build constraint | 1 failed | yes |
| 20 | empty constraint files accepted | 1 failed | yes |
| 21 | env check only `PIP_` (not `UV_`) | 1 failed | yes |
| 22 | python allowed as a shell | 1 failed | yes |
| 23 | `PIP_INDEX_URL` allowed in env | 1 failed | yes |
| 24 | expression-only run not reported | 193 passed | NO |
| 25 | blind-scan check removed | 1 failed | yes |
| 26 | composite actions not scanned | 1 failed | yes |
| 27 | pip.conf not refused | 1 failed | yes |
| 28 | function named pip not refused | 1 failed | yes |
Totals counted from the table: 28 mutants, 23 killed, 5 survived (1, 6, 11, 15, 24). Survivors run against the suite: nothing outside the c23 file imports the scanner (`git grep` for the module name finds no other user), so the c23 file is the whole suite for it; the 5 survive it. Classification: 15 is equivalent (my probe above shows `--find-links` is also refused by the long-option-prefix rule); 24 is equivalent for pass/fail (the same step is also refused by the "expression in command position" rule; only the message differs); 1 and 6 look equivalent by reading (a split on `|` twice gives the same statements; `(` is already replaced by a space) but I did not prove it; 11 is a true survivor (the accepted `--constraint=` spelling is not pinned as accepted).

## Findings
- F-C460-1 LOW: survivor 11, add one accept-case for `--constraint=file` (otherwise a regression turns a valid workflow red with no test naming why).
- F-C460-2 LOW: survivors 1 and 6 may be dead code in the scanner (not proven).
- F-C460-3 LOW: objections 1 and 3 are stated scope, nothing to fix.

## Verdict: PASS on e5317342aa3288153ef6f8b7a44abba372ce10c9
Head frozen; LOWs go in a NEW PR. Merge is clean against current main (base 5808a5cd is old), and the scratch merge passes both files (256). CI green and GX10 16/16 on this exact head rebased on current main per the coordinator procedure. Not run by me: CI, GX10.
