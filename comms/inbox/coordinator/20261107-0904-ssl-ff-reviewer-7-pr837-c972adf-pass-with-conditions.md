# Delta review PR 837 (G18 stage1_window) at the new head — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `c972adf47b608c8424b94bb1eb760784519d4fb4`.
My earlier conditions: **C1 CLOSED, C2 CLOSED** (C2 by the alternative I offered: the row now carries `window_end`; a future-dated window is also refused). New conditions found by my probes, both small and about the fail-closed claim: **N1** reject non-finite snapshot timestamps; **N2** reject a non-finite `--min-hours`. N1/N2 can land as a follow-up before G25 relies on the row, but I would rather they went in with this PR: both are one-line `math.isfinite` checks. Also C3: CI and GX10 on the landed head (CI itself is green: tests on 3.11 to 3.14, compose-smoke, fly-image-smoke, compose-upgrade-smoke).

## Checks (HIGH, run by me)
- Head is 4 commits on main ccd013d4 (current main): 81fd0e2d, 3a435b7a, fae56564 (a merge commit from the builder's own branch, no trailer; flag only), c972adf4. Author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on all 4; trailers Sonnet 5.5 where present; 0 files under .github/. Files: tools/stage1_window.py, tools/tests/test_stage1_window_g18.py, one runbook line (the 24 hour minimum and the command). Trial merge with main: clean; GitHub reports MERGEABLE.
- Tests on the exact head (Windows, Python 3.14): test_stage1_window_g18.py 53 passed (24 test functions, parametrized).
- C1 reproduced and closed: a one-service pair 48 h apart now FAILS with `<label>: missing from the before/after snapshot` for the seven absent labels; 8 before vs 7 after fails; 7 before vs 8 after fails; a snapshot holding only an unknown label fails (all eight reported missing). Eight services, 48 h, equal counters: clean. Increase: `dropped_refused_increase`, `dropped_unauth_increase`. Decrease: not clean (restart wording).
- C2: window ending 10 days in the future: "the window ends in the future" (skew 300 s). The row now has `window_end` (int epoch of the after snapshot), `window_hours` and `services` (8 in my run). A STALE pair (2023 timestamps) is still CLEAN by design; the age of the window is left to Stage 2 (G25), which can read `window_end`. This is the thing G25 must check: say so in its card. HIGH.
- N1 (new, reproduced): a snapshot whose `taken_at` is NaN (JSON `NaN`, which Python's json accepts) passes every time check, because every comparison with NaN is false: `evaluate_window` returns CLEAN for NaN/NaN and for NaN/now; `-Infinity` before with a normal after is also CLEAN (infinite window). Through the CLI with `--records` and NaN/NaN the tool prints `[PASS] the Stage 1 window is clean` and then dies with `ValueError: cannot convert float NaN to integer` (rc 1, nothing recorded): it fails closed by accident, after printing PASS. With NaN before and a real after, a G18 row can be written with `window_hours` NaN (not run by me to the end; I read the code path). Snapshots are local unsigned files and `snapshot` itself writes `time.time()`, so this needs a hand-edited or corrupted file: LOW to MEDIUM.
- N2 (new, reproduced): `--min-hours nan` disables the minimum: a 1-second window printed `[PASS]` and `recorded gate G18` (rc 0), the row has `window_hours: 0.0`. `--min-hours inf` is refused correctly. The `--min-hours < 0` guard does not catch NaN. The default (24) is safe; this needs a typed flag. LOW to MEDIUM, and it is exactly the "a forgotten flag is not clean" class the PR sets out to close.
- Suggested fix: in `evaluate_window`, treat a timestamp that is not `math.isfinite` as "does not run forward"; in `main`, refuse `not math.isfinite(args.min_hours)` with exit 2; add three tests (NaN timestamps, -inf before, `--min-hours nan`).

## Mutants (17 attempted, 16 applied; counted from the table; per condition)
| # | cond | mutant | result |
|---|---|---|---|
| C1a | C1 | label loop removed | KILLED |
| C1b | C1 | before side not checked | KILLED |
| C1c | C1 | after side not checked | KILLED |
| C1d | C1 | only seven labels required | KILLED |
| C1e | C1 | only labels already in before required | KILLED |
| C1f | C1 | only one label required | KILLED |
| C2a | C2 | future check removed | KILLED |
| C2b | C2 | skew 1e12 | KILLED |
| C2c | C2 | skew negative | KILLED |
| C2d | C2 | `now` argument ignored | KILLED |
| C2e | C2 | window_end dropped from the row | KILLED |
| C2f | C2 | window_end = before time | KILLED |
| C2g | C2 | window_hours dropped | KILLED |
| C2h | C2 | services count dropped | NOT APPLIED (search string did not match; not counted) |
| D1 | other | decrease check removed | KILLED |
| D2 | other | default min hours 0 | KILLED |
| D3 | other | min-hours boundary `<=` | KILLED |
Totals: 17 attempted, 16 applied, 16 killed, 0 survived, 1 not applied (16+0+1 = 17). Per condition: C1 6/6 killed, C2 7/7 applied killed (1 not applied). The mutants do not cover N1/N2: the tests have no non-finite case, so a NaN mutant would not be a mutation of the code but a missing check.

## Not verified
GX10 and Linux; a live `snapshot` against an estate (none run); whether any G25 code yet reads `window_end`; the whole tools suite on this head.
