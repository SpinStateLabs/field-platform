# Review PR 705 @ 6d28de421359f33aec494f3b415820bbb4ed992a (spend-governor: bound and clean a usage policy's allowed_models on write, S6-6) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head 6d28de42. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head rebased on current main still required.

## Objections first
1. The defect: a blank allow-list entry normalised to `''`, so a non-empty list held no real model and EVERY usage record was a `rogue_model` (each one opening a human escalation). The new code refuses blanks on write. The bounds are on WRITE only, so a stored legacy row with a blank entry still makes every model rogue at usage time (the PR chose compatibility with C-363); the test pins only that such a row still READS (201 on usage), not what the usage then flags.
2. The new 422s are `HTTPException` details written by this function, not the platform's validation handler (which drops messages). So the "never the names" promise depends on these f-strings; I probed (L5, N4).
3. The same endpoint's model (`UsagePolicy.allowed_models`) is also touched by PR 555 (`Utf8Str`); the merge of the two heads is clean in my trial below.

## Facts (HIGH)
- Head fetched via refs/pull/705/head = 6d28de42; 1 commit; three commits behind current main (no overlap); author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 2 files, +136 -1: `api.py` (`MAX_ALLOWED_MODELS = 200`, `MAX_MODEL_NAME = 200`, `_checked_allowed_models`, used in `PUT /policies/{id}`), `tests/test_policy_allowed_models_bounds.py` (+109, 15 cases).
- Baselines unmutated: new file 15 passed; whole spend-governor suite 306 passed.

## Mutants (the new file first; a survivor then the whole suite; file restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| the count bound: exactly 200 allowed, 201 refused (L2, L3, L4), the constant (L1), message without names (L5) | 5 | 3 | 2 (L1, L5) |
| the entry length bound: boundary (N2), removed (N3), no name in the message (N4), the constant (N1) | 4 | 3 | 1 (N1) |
| blank entries refused: removed, whitespace-only, the message (B1-B3) | 3 | 3 | 0 |
| canonical form, nothing-after-normalise refused, de-duplicated, order kept (C1, C2, D1, D2) | 4 | 2 | 2 (C2, D2) |
| the write path uses the helper (W1) | 1 | 1 | 0 |
Totals counted from the table: 5+4+3+4+1 = 17 rows; killed 3+3+3+2+1 = 12; survived 5 (L1, L5, N1, C2, D2).

## Survivors (each also survives the whole suite)
- F-R705-1 LOW-MEDIUM (L5): the count-bound 422 can repeat the first entries of the list and nothing fails; the tests check only that the limit number appears in the text. (N4, the sibling message, is pinned.)
- F-R705-2 LOW (L1, N1): the constants 200 and 200 are imported by the tests, so they are not pinned as numbers.
- F-R705-3 LOW (D2): the order of the canonical list is not pinned (the test input is already alphabetical, so sorting passes).
- F-R705-4 LOW (C2): the "entry normalises to nothing" branch has no test; I did not find an input that reaches it with a non-blank string (I do not know `normalize_model`'s full behaviour), so it may be dead.
- F-R705-5 LOW (objection 1): a legacy stored row with a blank entry keeps flagging every model as rogue; the PR leaves it; the coordinator may want a migration or a read-time skip of blank entries as a follow-up.

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head rebased on current main.
