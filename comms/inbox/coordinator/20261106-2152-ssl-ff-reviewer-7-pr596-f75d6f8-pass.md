# Review PR 596 (S2-11: sealed-ledger `interval_from_env` never raises on non-ASCII digits) — ssl-ff-reviewer-7

**VERDICT: PASS** on head `f75d6f8dccf7dfd7f57b5ea78b26927df50d8100` (no conditions beyond the standard CI and GX10 on the landed head).

## Checks (HIGH, run by me)
- Identity: 2 commits, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on both; trailers Sonnet 5.5; .github/: 0 files. 2 files: sealed_ledger/operator_observer.py (+6/-2), tests/test_operator_observer_interval_env.py (+31). Based on 97dcfec1; main is 250154d3; a trial merge into current main is clean.
- Code read: `interval_from_env` accepts only `[0-9]+` by `fullmatch` after a strip, guards `int()` against ValueError (a digit string past the interpreter's conversion limit), returns None unless the value is positive, and floors a valid value at `MIN_EVERY_S` (5). `isdigit()` was True for `²`, `③`, `①`, which `int()` rejects, and `create_app` calls `from_env` unguarded, so a bad `FIELD_LEDGER_OBSERVE_EVERY` stopped the ledger at start.
- My table of inputs through the real function (value -> result): `120` -> 120; ` 120 ` -> 120; `120\n` -> 120; `1` -> 5; `0`, `-5`, `+5`, `12.5`, `1e3`, `1_000`, `0x10`, `1 2`, empty and blank -> None; `²`, `③`, `①`, `1²` -> None; full-width `５０`, `００１２０`, Arabic-Indic `٣` and `٠٠٣`, Devanagari `१२०` -> None; a 5000-digit string -> None. None raises.
- Behaviour change to note (intended by the PR, second commit): non-ASCII digits that `int()` DOES accept (full-width, Arabic-Indic, Devanagari) used to arm the observer with that value and now arm nothing. Consistent with docs/ENVIRONMENT.md ("digits only, > 0 seconds, minimum 5; anything else (0, blank, junk) = off"). An operator typing such digits gets the observer silently off, as for any junk value: no warning is logged (LOW; a one-line warning would help).
- Tests on the exact head (Windows): the new file plus test_operator_observer_c6.py 58 passed; `environment_anchors --check` 0 wrong rows. The PR notes `test_operator_observer_c6_serve.py` errors on clean main here too (a `ledger serve` subprocess exits early); not touched by this change and not re-run by me.

## Mutants (9 on interval_from_env vs the two observer test files; counted from the table)
| # | mutant | result |
|---|---|---|
| I1 | `isdigit()` again (old behaviour) | KILLED |
| I2 | unicode digits allowed (`\d`) | KILLED |
| I3 | `match` instead of `fullmatch` | KILLED |
| I4 | a leading sign allowed (`[+-]?[0-9]+`) | SURVIVED |
| I5 | strip dropped | KILLED |
| I6 | `int()` not guarded | KILLED |
| I7 | zero accepted (floored to the minimum) | KILLED |
| I8 | minimum floor removed | KILLED |
| I9 | floor off by one | KILLED |
Totals: 9 mutants, 8 killed, 1 survived (8+1 = 9). I4 is a LOW pin gap: nothing asserts that `+5` is refused (`-5` is refused anyway by the positivity check), so `+5` would arm the observer at 5 seconds under that mutant.

## Not verified
CI/GX10; Linux; the whole sealed-ledger suite on this head.
