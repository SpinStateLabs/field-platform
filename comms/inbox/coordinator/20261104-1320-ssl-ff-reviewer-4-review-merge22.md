# Reviewer note (FALLBACK, read-only): MERGE 22 = main 4ef319cc (PR 470 head itself, C-1183: pins for the C-1151 mutation-sweep survivors)
Reviewer: ssl-ff-reviewer-4. UNVERIFIED (cloud, no GX10). Read-only: nothing pushed or changed outside comms. Delta reviewed: c356e205..4ef319cc, tests only, 4 files (+93/-1): test_422_handler_installed_c1114.py, test_boundary_echo_lint_c505.py, test_environment_anchors_c1116.py, test_http_env_proxy_lint_c57.py. All 5 commits (4ef319cc, 2512e9db, aed915d5, aa0a4295, 07ebc585): author and committer Don Hagell 13129187+dhagell@users.noreply.github.com, trailers Sonnet 5.5 (HIGH). The merge is already done; this note is an independent mutant check after the fact and does not reopen it. The 3 earlier-recorded verdicts (Lane 7 Q-116, GX10 B 16/16) are not re-run.

## Baseline
The four files at 4ef319cc: 236 passed (relative PYTHONPATH, all services on the path).

## Mutants (scratch worktree at 4ef319cc; kill = at least one failure in the four files)
| # | Mutant (behaviour pinned by the delta) | Result | Killed |
|---|---|---|---|
| A09a | anchor-on-last-line bound `<=` -> `<` (mention branch) | 1 failed | yes |
| A09b | lower bound 1 -> 0 | 236 passed | NO |
| A09c | stale-branch bound `<=` -> `<` | 236 passed | NO |
| A09d | mention test inverted | 4 failed | yes |
| A10a | ambiguous cell `!= 1` -> `< 1` | 1 failed | yes |
| A10b | `!= 1` -> `> 1` (a cell with zero matches no longer refused) | 236 passed | NO |
| A10c | rewrite the whole line, not the last cell | 1 failed | yes |
| A10d | replace first occurrence only | 236 passed | NO |
| A15a | SyntaxError fallback returns nothing | 2 failed | yes |
| A15b | fallback counts comment lines | 1 failed | yes |
| A15c | fallback matches substrings | 236 passed | NO |
| A15d | ValueError no longer caught | 236 passed | NO |
| B13 | `extra=` keyword no longer exempt | 1 failed | yes |
| B15 | `note` removed from FIELD_KEYWORDS | 1 failed | yes |
| B16 | `warn` removed from LOG_METHODS | 1 failed | yes |
| B17 | `msg` removed from FIELD_KEYWORDS | 236 passed | NO |
| B18 | `critical` removed from LOG_METHODS | 236 passed | NO |
| S1 | call under `if` counts as an install | 1 failed | yes |
| S2 | any argument name counts | 1 failed | yes |
| S3 | returned-name requirement dropped | 1 failed | yes |
| S4 | argument-is-a-Name check dropped | 1 failed | yes |
| S5 | FastAPI-binding requirement dropped | 236 passed | NO |
| P1 | floor MIN_FILES 100 -> 10 | 1 failed | yes |
| P2 | headroom 20 -> 2000 | 1 failed | yes |
| P3 | the test_the_scan_is_not_blind assertion weakened to `>= 1` (mutation of TEST code) | 236 passed | NO |
| P4 | `assert MIN_FILES >= 100` removed (mutation of TEST code) | 236 passed | NO |
Totals counted from the table: 26 valid mutants, 15 killed, 11 survived (A09b, A09c, A10b, A10d, A15c, A15d, B17, B18, S5, P3, P4). My S6 did not apply (pattern matched twice) and is excluded. P3 and P4 mutate the test code itself, so no test can kill them: excluding them leaves 24 mutants, 15 killed, 9 survived. Survivors against the whole suite: I ran only the four files (the delta touches only these), so "survives" means these four files.

## Reading
- The delta's own claims, i.e. the three boundary-lint survivors B13, B15, B16 (3/3), the 422 serving-app reading S1-S4 (4/4), the anchors last-line bound A09a and A09d, the `count != 1` refusal against a duplicate A10a/A10c, the SyntaxError fallback A15a/A15b, and the floor P1/P2: all KILLED.
- True gaps left (LOW, not blocking, follow-up PR): A10b (a cell that does not hold the target at all is not pinned as refused), A15c and A15d (substring match and NUL-byte handling in the fallback), A09b and A09c (edges of the line-number bounds; A09c changes only the message text), S5 (a returned name that is not bound to `FastAPI(...)` is not refused). A10d is equivalent when the count is 1. B17 and B18 are not claimed by C-1183.

## Verdict (retrospective, no head to freeze): no objection to MERGE 22
The claimed pins hold under mutation; 9 residual gaps are LOW and go in a NEW PR if wanted.
