# Review R-PR1045-bee3ba4
**VERDICT: PASS** for head bee3ba48e023ebf2735f576a750c6689e5190afa (S12-29, fly_identity_check: a non-object /health body is a C5-RESULT FAIL, not a traceback)

Reviewer: fp-reviewer-b. Independent (did not build this PR).

## Checks
| Check | Result | Confidence |
|---|---|---|
| Head equals PR head | yes | HIGH |
| Author and committer | Don Hagell 13129187+dhagell noreply, 1 commit | HIGH |
| Files | tools/fly_identity_check.py (+6/-1), tools/tests/test_fly_identity_health_shapes_s12.py (+82); 0 under .github/ | HIGH |
| Secrets / estate addresses | none in added lines | HIGH |
| Behind main | 15 commits, `merge-tree` clean | HIGH |
| Docs cites into the script | none | HIGH |
| Lints (boundary-echo, blindspots, http-env-proxy, no-line-cites, environment-doc, environment-anchors) plus the two tests that import the script | 401 passed, 9 skipped, 1 failed (below) | HIGH |
| New tests | 27 passed | HIGH |
| The one failure: tools/tests/test_fly_identity_c5.py::test_absent_secrets_are_byte_identical_to_origin_main ("argv differs from origin/main", 28 more items) | fails identically on main in this Windows environment; in a file this PR does not touch; not attributable | HIGH |

## Behaviour measured on the head (stubbed /health bodies through `_health` and `check_health`)
| Body | Result |
|---|---|
| `null`, a list, a number, a string, `true` (the PR's cases) | marker `NotAnObject`, one named problem per service, `C5-RESULT: FAIL`, exit 1 (tests) |
| 30,000 nested `[` | marker `RecursionError`, no escape |
| invalid UTF-8 | marker `UnicodeDecodeError` |
| truncated JSON, empty body | marker `JSONDecodeError` |
| object with `NaN`, a list id, a 60,000-character id | read as objects; one problem per service in `expect none`; nothing escapes |
| `identity_present: "false"` (string) with `expect none` | flagged (the comparison uses truthiness, so the string counts as present; fails safe) |
Nothing escaped as a traceback in any of these. The generic `except Exception` in `_health` is what keeps the nested and malformed cases safe, and it is not covered by a test (mutant X11).

## Mutants (scratch copies, tests/test_fly_identity_health_shapes_s12.py)
| # | Mutant | Result |
|---|---|---|
| X1 | `_health` keeps any body | KILLED |
| X2 | marker text changed | KILLED |
| X3 | `check_health` guard dropped | KILLED |
| X4 | message drops the type name | KILLED |
| X5 | guard `continue` dropped | KILLED |
| X6 | list passes the guard | KILLED |
| X7 | truthiness instead of `isinstance` in `_health` | KILLED |
| X8 | marker key renamed (would fail open) | KILLED |
| X9 | health problems not added to the result | KILLED |
| X10 | mismatch count fixed at 0 | KILLED |
| X11 | exception handler narrowed to OSError | SURVIVED |
| X12 | read cap raised from 64 KiB | SURVIVED |
| X13 | one bad service stops the loop | KILLED |
| X14 | FAIL line not printed | KILLED |
| X15 | exit code 0 on failure | KILLED |

Totals: applied 15, killed 13, survived 2, not applied 0. Baseline 27 passed.

## Optional LOWs (new PR, not conditions)
1. X11: add invalid-JSON, invalid-UTF-8 and deeply nested bodies to the `_health` tests so the broad handler is pinned.
2. X12: the 64 KiB read cap has no test.
3. `identity_present` is compared by truthiness, so `"false"` counts as present. A strict `is True` comparison would be safer; I did not check whether any service sends a non-boolean there.
