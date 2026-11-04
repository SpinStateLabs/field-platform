# Review PR 596 @ e21a0c3099f7b21205856fcd5aaaaf01d681fdd0 (sealed-ledger: interval_from_env takes only ASCII digits and never raises, S2-11) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS WITH CONDITIONS** on head e21a0c30. UNVERIFIED (cloud, no GX10). The condition is one missing pin for the title's "only ASCII digits".

## Objections first
1. The title says "takes ONLY ASCII digits". The regex `[0-9]+` is followed by `int(raw)`, which also rejects most non-ASCII junk, so the regex is partly redundant with the new `except ValueError`; whether the "only ASCII" half is pinned depends on a digit that int() ACCEPTS (Arabic-Indic, e.g. U+0661). The tests contain none (A1/A3 survive).
2. 5000-digit strings: `int()` raises `ValueError` past the interpreter's conversion limit (default 4300 digits, general knowledge, MEDIUM, interpreter-setting dependent). On an interpreter with the limit disabled the huge value would be accepted and floored; the test would then fail on that host, not on a bug.
3. `from_env` reaching `create_app` at start is the stated blast radius; one test pins `(None, None)` for `²`.

## Facts (HIGH)
- Head fetched via refs/pull/596/head = e21a0c30; 1 commit; its base is origin/main 97dcfec1 (main has since moved 1 commit, `b963407a`, in `tools/start_role_session.py`: no overlap); author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>. `operator_observer.py` +6 -2, `tests/test_operator_observer_interval_env.py` +22 (new).
- Baseline unmutated: the 5 observer test files = 101 passed. The full sealed-ledger suite gave 818 passed, 5 skipped, 1 error: the error is `test_operator_observer_c6_serve.py` ("ledger serve exited early", it spawns a subprocess my environment cannot run); excluded from the table, not counted as a pass.

## Mutants (the 5 observer files each time; files restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| digits only (A1 isdigit, A2 prefix match, A3 `\d`, A4 allows empty, A5 trailing newline) | 5 | 0 | 5 |
| a digit string past the int limit never raises (B1, B2, B3) | 3 | 3 | 0 |
| positive, floored at MIN_EVERY_S (C1-C5) | 5 | 5 | 0 |
| strip and None (D1-D3) | 3 | 3 | 0 |
Totals counted from the table: 5+3+5+3 = 16 rows; killed 11; survived 5; anchor failures 0.

## Survivors
- A2, A4, A5 are EQUIVALENT in output: the prefix, empty and newline shapes still reach `int()`, which raises `ValueError`, and the new handler returns None (I traced the code path: the strip removes a trailing newline first).
- F-R596-1 LOW-MEDIUM (A1, A3): with `isdigit()` or `\d` a string like U+0661 U+0662 (Arabic-Indic digits for 12) passes `int()` and ARMS the observer at 12 seconds, contradicting the title's ASCII-only rule. No test has such a value; the PR's own comment says `isdigit()` "takes '²' and '①', which int() rejects", which is the case the tests cover. Add one Arabic-Indic case to the "not a positive ASCII integer" list.
- Not run against the whole suite: the survivors are in the observer files only; I grepped the test tree for other users of `interval_from_env` and found only the five files used (not run elsewhere).

## Conditions
1. Pin F-R596-1 (one parametrize value) before this lands, or the coordinator rules it a follow-up.
2. GX10 16/16 and CI on this head rebased on current main.
