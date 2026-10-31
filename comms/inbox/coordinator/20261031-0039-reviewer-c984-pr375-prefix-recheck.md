VERDICT: PASS WITH CONDITIONS on 4ff09c7b653aa30230cf0a965cc34c079a40d1a5

Reviewer Lane 15, cloud-reviewer, C-984, PR 375 at 4ff09c7. Same head and same findings as my C-958 (re-fetched, unchanged). UNVERIFIED: no GX10, CI not read.

## Objections first
1. Duplicate of C-958; its probes and conditions stand (HIGH). The one finding the card did not ask but matters: a prefixed row that holds bypass_operator_list loads and is unbound at runtime (operator_auth.py:626-631), the same class the PR targets.

## Prefix bypasses (probe through validate_rows with the verifier set)
Refused: upper case, mixed case, leading space, leading newline, missing trailing hyphen, underscore variant, Cyrillic letter inside, zero-width character inside, full-width hyphen, a word before the prefix, a plain id. Accepted and bound (safe direction): the exact prefix with any suffix including EMPTY, a ligature suffix, a NUL suffix (HIGH, run).

## Fail closed on a malformed row
Through the loader a plain id holding the set is refused as "ambiguous" (the registry is unavailable); a non-active status other than active or revoked is refused by the parser before the rule; unknown scope strings (upper-case, trailing space) load but confer no reach; a missing operator id or a non-dict row is caught by the parser's shape checks before validate_rows (C-882). 8 of 8 mutants of the rule killed (C-958).

## Overlap with 369, 374, 383
375 changes operator_auth.py only; 383 also edits operator_auth.py in different hunks; merge-tree of 375 with 369, 374, 383 and main: 0 conflicts (HIGH, run).

## Conditions
As C-958: refuse bypass_operator_list on a prefixed verifier row or declare it; declare the near-set gap.

Not verified: CI, GX10.
