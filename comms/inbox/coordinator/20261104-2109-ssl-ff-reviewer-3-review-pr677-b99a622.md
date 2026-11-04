# Review PR 677 @ b99a622dfc9929de793c57cf314e3eb214ac84e0 (lifecycle-manager: FIELD_WITNESS_EVERY is ASCII digits only and capped at 10**9, S5-1) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS WITH CONDITIONS** on head b99a622d. UNVERIFIED (cloud, no GX10). Condition 1 is a measured defect: a digit string longer than the interpreter's int-conversion limit still raises, against the PR's own claim.

## Objections first
1. The PR and its test file say a bad value is "the 'misconfigured' finding, never an exception". I tried the inputs the claim covers and one more: a 5000-character ASCII digit string.
2. The same class was fixed for the sealed-ledger observer in PR 596 (a digit string "past the interpreter's int-conversion limit"); the tests there pin `"9" * 5000`. Here the longest test value is `"9" * 40`.
3. The cap of 10**9 seconds is argued from "3 x it must still fit a timedelta"; the test proves the largest allowed value does not overflow the staleness math.

## Facts (HIGH)
- Head fetched via refs/pull/677/head = b99a622d; 1 commit; four commits behind current main (no overlap with these two files); author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 2 files, +86 -1: `engine.py` (`MAX_WITNESS_EVERY_SECONDS = 10**9`; the parse now `raw.isascii() and raw.isdigit()` plus the bound), `tests/test_witness_env_digits.py` (+80, 33 cases).
- Baselines unmutated: new file 33 passed; whole lifecycle-manager suite 302 passed.
- MEASURED on the head (`witness_watch_from_env({"FIELD_WITNESS_EVERY": v})`): `²` -> None; `٣` (Arabic-Indic) -> None; `5` -> 5; `0` -> None; `1000000000` -> 1000000000; `1000000001` -> None; `-1` -> None; ` 7 ` -> 7; `1_0` -> None; 4300 nines -> None; **5000 nines -> RAISES ValueError** (the digit check passes and `int()` refuses the length). So the function can still raise from the environment at start, which is what the PR set out to prevent.

## Mutants (the new file first; a survivor then the whole suite; file restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| ASCII digits only: `isdigit` alone, `isascii` alone, `\d` (A1-A3) | 3 | 3 | 0 |
| bounded: 10**9 exactly, +1, -1, removed, `<`, zero allowed, 10**12 (B1-B6) | 6 | 6 | 0 |
| an over-long digit string never raises: add a `try/except ValueError` around `int()` (C1) | 1 | 0 | 1 |
| strip, blank is no witness, raw kept, estate default (D1-D4) | 4 | 4 | 0 |
Totals counted from the table: 3+6+1+4 = 14 rows; killed 13; survived 1 (C1).

## Findings
- F-R677-1 MEDIUM (measured, C1): `FIELD_WITNESS_EVERY` of more than 4300 ASCII digits (the default interpreter limit, general knowledge, MEDIUM; the limit is configurable) raises `ValueError` out of `witness_watch_from_env`, where PR 596 and this PR's claim say it must not. Fix: check the length (`len(raw) <= 10` is enough for a 10**9 cap) before `int()`, or catch `ValueError`; add `"9" * 5000` to the unusable-values list.
- F-R677-2 LOW: `1_0` and `+5` are refused by the new rule (they were also refused or crashed before); pinned.

## Conditions
1. Fix and pin F-R677-1 before this lands.
2. GX10 16/16 and CI on this head rebased on current main.
