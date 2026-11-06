# Review PR 495 (scout S-B2: force-gateway junk hygiene/budget env settings fall back to defaults) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `466004db8f7f9eed245e9a0dfceaab46b535e6e5`.
Conditions: C1 add one assertion for the explicit `latency_budget_ms` argument (see mutant A19; non-blocking, can follow). C2 CI and GX10 on the landed head (Linux not verified). C3 Don rules on cooldown 0 (the PR's own open question; code allows 0).

## Checks (HIGH, run by me)
- Identity: 3 commits (5e6f11cf, 95e29cf6, 466004db), author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on all; trailers Sonnet 5.5; 0 files under .github/. 3 files: api.py (+29/-5), new test file (+58), docs/ENVIRONMENT.md (+11/-11).
- Trial merge with main 41afda502 (merge-base cd3b7690): clean. `tools/environment_anchors.py --check` on this head: 0 wrong anchor rows.
- Code: `_env_int(name, default, minimum)` and `_env_float(name, default, positive=True)` catch ValueError, refuse NaN/inf (float) and out-of-range, return the default; the five settings use them; no default changed (5, 0.15, 2, 250.0, 10 as before). Explicit `create_app(...)` args still win. `drift=` injected skips env, as before. Float "1e999" parses to inf and is refused; int "2.5" raises ValueError and falls back.
- Tests on exact head (Windows, Python 3.14): test_hygiene_env_guard_sb2.py 49 passed (~55 s; create_app is slow). The PR reports the force-gateway suite 497 passed; I did not re-run it.
- Doc rows updated to match (fallback, never stops startup, "nothing is logged" is true: no log call in the resolvers).

## Mutants (19, single-line, green baseline; counted from the table)
| # | mutant | result |
|---|---|---|
| A1 | finite check dropped | KILLED |
| A2 | positive range check dropped | KILLED |
| A3 | positive allows 0 | KILLED |
| A4 | int minimum ignored | KILLED |
| A5 | int minimum off by one | KILLED |
| A6 | float ValueError not caught | KILLED |
| A7 | int ValueError not caught | KILLED |
| A8 | window minimum 0 | KILLED |
| A9 | baseline minimum 0 | KILLED |
| A10 | cooldown minimum 1 | KILLED |
| A11 | default window changed | KILLED |
| A12 | default band changed | KILLED |
| A13 | default budget changed | KILLED |
| A14 | default cooldown changed | KILLED |
| A15 | default baseline changed | KILLED |
| A16 | band allows zero | KILLED |
| A17 | budget allows zero | KILLED |
| A18 | explicit cooldown arg ignored | KILLED |
| A19 | explicit latency_budget_ms arg ignored | SURVIVED |
Totals: 19 attempted, 18 killed, 1 survived (18+1 = 19), 0 not applied. A19 is a real pin gap: `test_explicit_arguments_still_win_over_the_environment` passes `latency_budget_ms=5.0` but asserts only `bypass_cooldown`; assert `state.latency_budget_ms == 5.0` (and set the env junk for it) to close it.

## Not verified
CI/GX10; Linux; whole force-gateway suite on this head; the other gateway env parsers the PR says it did not audit (sample_every, retain, sentinel timeout).
