# Review PR 374 @ b97d35fc70479b6089f579eceea8973967f52274 (C-801, internal-only secret for the two internal operator routes) - reviewer ssl-ff-reviewer-3

**VERDICT: BLOCK on head b97d35fc as a branch (lineage). The patch passes on a clean rebuild; one LOW-MEDIUM survivor. UNVERIFIED (cloud, no GX10).**

## Blocking finding (HIGH, measured)
- F-R374-1 BLOCK: no merge base with current origin/main (97dcfec1; `git merge-base` fails); `git log origin/main..pr374` lists 423 commits (old pre-rewrite history, as PRs 383, 387, 392, 405, 408, 419, 420).
- The PR's own work is 8 commits above 63e91b21 (0584c844, c29eabe5, 1eb21c71, f1a6c5b1, 470bea50, 09abbe36, 689476a7, b97d35fc), all Don Hagell noreply for author AND committer (measured).

## The patch, measured on a clean rebuild (main 97dcfec1 + `git cherry-pick 63e91b21..pr374`, no conflict, 3 files, +320 -3)
- `operator_health.py` (+63): `internal_secret_problem()` (checked at install), `internal_request_allowed()` (the gate), two env names, header `x-field-internal`; `docs/ENVIRONMENT.md` (+2 rows); `tests/test_operator_internal_secret_c801.py` (258 lines, 20 tests).
- Baseline unmutated: the whole field-core suite 1574 passed, 2 skipped (relative `PYTHONPATH=src`).
- Mutants of `operator_health.py`; every row ran the WHOLE field-core suite (files restored, worktree clean):
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| gate on both routes; perimeter first; install refuses a bad setup; wire header name (G1-G6) | 6 | 5 | 1 (G5) |
| `internal_request_allowed`: no secret = open, empty never passes, hash form, value form, both must match, constant-time compare, malformed hash fails closed (A1-A11) | 11 | 11 | 0 |
| `internal_secret_problem`: bad hash, empty-string hash, non-printable value, equals the perimeter secret (value and hash), no secret in the text (P1-P10) | 10 | 10 | 0 |
Totals counted from the table: 6+11+10 = 27 rows; killed 5+11+10 = 26; survived 1; anchor failures 0.

## Survivor
- F-R374-2 LOW-MEDIUM (G5): changing the literal `INTERNAL_HEADER = "x-field-internal"` to another name passes all 1574 tests, because the tests read the constant. The wire name is a contract with the rotator and with ENVIRONMENT.md (the doc row names `x-field-internal`); nothing pins the literal. A one-line pin (`assert INTERNAL_HEADER == "x-field-internal"` plus a request using the literal) closes it. Optional, NEW PR only.

## Findings
- F-R374-3 LOW (read, not run): `internal_request_allowed` returns early on an absent header, so an unauthenticated caller can learn whether an internal secret is configured only through response timing, which the doc says answers the same 404 as an off route; I did not measure timing. I do not know whether that matters here.

## Recommendation (coordinator's call)
Release PR 374; rebuild by `git cherry-pick 63e91b21..pr374` on current main (clean today) as a new draft PR; fresh independent review on that head. Security-sensitive: the rebuilt PR should add the F-R374-2 pin before landing.

## Objection
Approving the old head would approve an unmergeable branch; this verdict covers the rebuilt patch only.
