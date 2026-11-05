# Review PR #773 (delegation-authority DOA max_ttl_days <= 3650, S8-16) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `98a32dfc6184f06d6cfdc643a09bad8777747b3e` (draft, base main). Optional LOWs go in a NEW PR.

## Facts (HIGH, read from the head)
- 1 commit, 3 files: delegation_authority/doa.py (+6/-1), README.md (1 line), tests/test_doa_max_ttl_bound_s8.py (+89). Nothing under .github/. Author AND committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- `GrantorRow.max_ttl_days: int = Field(gt=0, le=MAX_TTL_DAYS)`, `MAX_TTL_DAYS = 3650`. The only use is the lifetime check `timedelta(days=row.max_ttl_days)` (api.py:305); with the load bound it cannot overflow, so omitting the card's extra guard there is sound (every roster path goes through GrantorRow).
- Fail-closed direction (HIGH): the change only adds a refusal. Side effect to know: ONE bad row makes the whole roster unloadable, so EVERY grantor's mint answers 503 (existing behaviour for any invalid row; the PR states it for the row, not for all grantors). 
- Repo rosters use 1 to 31 days (grep of manifests/doa-roster.example.yaml, upgrade-smoke fixture, docs): none near the bound. Estate rosters not visible to me (not in source).
- tests/test_doa_max_ttl_bound_s8.py: 12 passed on the head. Full delegation-authority suite (PR says 269) not run by me.

## Mutants (doa.py, one at a time, restored after each)
| # | Mutant | Result |
|---|--------|--------|
| M1 | upper bound removed | RED |
| M2 | `le` to `lt` | RED |
| M3 | MAX_TTL_DAYS 3651 | RED |
| M4 | `gt=0` to `ge=0` (admits 0) | SURVIVED |
| M5 | MAX_TTL_DAYS 10**9 | RED |
| M6 | MAX_TTL_DAYS 999999999 | RED |
Totals counted from the table: 6 mutants, 5 RED, 1 SURVIVED.

## LOWs (optional, new PR)
1. M4: a zero or negative `max_ttl_days` is not tested (the lower bound is pre-existing, but the field line was rewritten here). Add 0 and -1 to the refusal parameters.
2. Open decision (author's): 3650 as the ceiling; also reconcile with S3-22's roster-generator bound (author did not read it; I did not either: not in source).
3. README says "a larger value makes the roster unloadable (mint 503)": add that this holds for every grantor, not just the row.
