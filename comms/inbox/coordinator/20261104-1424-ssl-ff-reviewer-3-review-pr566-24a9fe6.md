# Review PR 566 @ 24a9fe64cb17098414dbfe07c968d72ac7517c54 (spend-governor: the resolve route's docstring is a real docstring) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head 24a9fe64. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head still required.

## Objections first
1. The change MOVES an executable line (`bind_body_operator`) below the docstring. A move can drop the line or reorder it relative to the `try`. Probed (A2, A6).
2. The AST scan has no negative corpus: it is itself the test, so a weakened scan cannot be caught by this file. I measured this directly (T-rows below).
3. The scan covers `spend_governor/api.py` only; the PR says it found "the only occurrence outside sealed-ledger" with a repository-wide scan, which I did not rerun (not in source).

## Facts (HIGH)
- Head fetched via refs/pull/566/head = 24a9fe64; 1 commit; base origin/main 97dcfec1 (main has since moved one unrelated commit); author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>. `api.py` +1 -1 (one statement moved), `tests/test_resolve_docstring_openapi.py` +41 (new).
- Baseline unmutated: the new file 2 passed; the whole spend-governor suite 293 passed.
- Red first, measured: with main's `api.py` restored the new file gives 2 failed (the OpenAPI description test and the scan), so both tests detect the original bug.

## Mutants
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| bug restored (statement before the docstring) (A1) | 1 | 1 | 0 |
| docstring text reaches OpenAPI: "First resolver wins", 409, idempotent (A3, A4, A5) | 3 | 3 | 0 |
| `bind_body_operator` still runs before the store call (A2 removed, A6 moved into a try) | 2 | 0 | 2 |
Totals counted from the table (whole spend-governor suite each time): 1+3+2 = 6 rows; killed 4; survived 2; anchor failures 0.
- Mutants of the scan itself (T1 `body[2:]`, T2 never flags, T3 skips decorated routes, T4 asserts nothing, T6 wrong constant type; run with the buggy `api.py` in place, only the scan test selected): 5 of 6 survive (T5 async-only was killed). That is by construction: the file has no test that feeds the scanner a known-bad input. T1 is the interesting one: the bug sits at body index 1, so `body[2:]` would miss it, and nothing pins the `[1:]`. (I first ran these with the whole file, where the OpenAPI test fails on the buggy source and made them all look killed; I discarded that run.)

## Findings
- F-R566-1 MEDIUM-LOW (A2): removing `req.resolved_by = operator_auth.bind_body_operator(req.resolved_by)` from `resolve` passes all 293 tests, so no test pins that the resolving human is bound to the caller's operator identity on this route. Pre-existing (the line is only moved here, not changed), but this PR touched it. A behaviour test belongs in a follow-up.
- F-R566-2 LOW (T1-T4, T6): the scan has no negative corpus; add `scan(source)` with one bad snippet asserting a finding.
- A6 (the bind inside a `try`) is EQUIVALENT in effect for the tests.

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head rebased on current main. F-R566-1 and -2 go in a NEW PR.
