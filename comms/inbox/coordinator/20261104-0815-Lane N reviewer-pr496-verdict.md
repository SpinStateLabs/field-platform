# Reviewer (lane B, delegation): PR 496 (scout P-9) empty agent_id lists nothing; tokens ordered by instant

**Verdict: PASS WITH CONDITIONS on head `666b86283e8087a4c89080f5a722c04d3d0ac5c1`.** Head unchanged at start and end (git ls-remote); base main cd3b7690; 1 commit, Don Hagell noreply on author and committer. Not built by this lane.

Diff (HIGH, read): store.py `TokenStore.list`: `if agent_id:` becomes `if agent_id is not None:`, and the result is `sorted(..., key=lambda t: t.issued_at)` (+3/-2); new `test_list_tokens_filter.py` (6 tests). Callers: api.py:183 (`/health` token_count, `len(_store().list())`), :365 (`GET /tokens`), store.py:160 (`active_tokens_for`).

## Objections first
1. REGRESSION: `sorted(key=t.issued_at)` raises `TypeError: can't compare offset-naive and offset-aware datetimes` when the table holds one naive and one aware `issued_at`. Measured on the PR head: `list()` raised TypeError; on main cd3b7690 the same two rows listed fine (2 returned). `DelegationToken` and `save` accept a naive `issued_at` (field-core delegation.py:30, no validator seen); the API mints with `now` (api.py:341), so only pre-existing, imported or direct-store rows can be naive (reachability MEDIUM; the failure surface is `/tokens`, `/health`, `active_tokens_for` and every caller of `list()`).
2. `active_tokens_for("")` now returns nothing instead of every active token: intended, noted by the author.
3. Case-insensitive match is not excluded: a `LIKE` variant of the filter would pass (unpinned, LOW).
4. The ordering test has 2 rows, so a wrong sort key passes by chance (survivor below).

## Measured (GX10 ~/ff-work/wt-ln496, relative PYTHONPATH, own venv with typer, python -B)
New file 6 passed. delegation-authority suite: PR 263 passed; main cd3b7690 257 passed (+6, no count down). CI when read: see Conditions. 16-suite not run by me.

## Mutants (27 rows; source restored, worktree clean)
| Behaviour pinned | Killed | Survived |
|---|---|---|
| B1 empty agent_id matches nothing | 5 | 0 |
| B2 no agent_id lists everything | 4 | 0 |
| B3 unknown agent matches nothing | 3 | 1 (`LIKE ?`: equals for these ids, case-insensitivity unpinned) |
| B4 a known agent lists its active and revoked tokens | 4 | 0 |
| B5 the API returns [] for an empty agent_id | 3 | 1 (equivalent: maps "" to a literal that matches no agent) |
| B6 tokens ordered by instant | 5 | 1 (sort by token_id: random uuids, 2 rows, passes about half the runs) |
Totals counted from the table: killed 5+4+3+4+3+5 = 24; survived 0+0+1+0+1+1 = 3; 27 rows. B3 and B5 have 3 kills each, under 4.

## Conditions
- C1: CI 7/7 SUCCESS on this exact head.
- C2: GX10 16-suite 16/16 on a head containing main.
- C3 (condition fix, the only push allowed): make the sort key total over mixed tz-awareness, for example `t.issued_at if t.issued_at.tzinfo else t.issued_at.replace(tzinfo=timezone.utc)` (naive means UTC, as `incident_replay._instant` does), with one test holding a naive and an aware row; or show that a naive `issued_at` can never reach the store and say so in the test.

## Findings (non-blocking; new PR only)
- F-496-1 LOW: a 3+ row ordering test (or equal-instant ties) so a random key cannot pass.
- F-496-2 LOW: a case-sensitivity test on the agent filter.
