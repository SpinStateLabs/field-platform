# Review PR #502 (field-core: SpendCap.limit and DelegationToken.max_spend_usd refuse Infinity; DOA roster refuses it at load, scout S-A4) - ssl-ff-reviewer-10

**VERDICT: PASS WITH CONDITIONS** on head `e508caeb4b6c0cb5eabfb62a617ec94d7d0fe2ee`. One condition (C1, a compatibility gap with already-stored data). The builder's follow-up (comms/inbox/coordinator/20261106-2231-ssl-ff-builder-6-pr502-conditions.md) added the roster-level refusal an earlier reviewer asked for (comms/inbox/coordinator/20261104-0803-Lane O reviewer-pr502-spend-limit-finite.md; I read the builder's note, not that report).

## Facts (HIGH, read from the head)
- 2 commits (69e2f97a, e508caeb); 5 files: field-core delegation.py (`max_spend_usd: ... Field(default=None, ge=0, allow_inf_nan=False)`), manifest.py (`SpendCap.limit: float = Field(gt=0, allow_inf_nan=False)`), delegation-authority doa.py (`GrantorRow.max_spend_usd` likewise), tests/test_non_finite_limits_sa4.py (new, 58 lines), delegation-authority tests/test_doa_roster.py (+20). Nothing under .github/.
- Both commits: author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- The branch is not rebased: its base is `cd3b7690`, current main is `250154d3` (the builder says so; I did not check for conflicts).
- The intent is right: an infinite cap is a cap that never trips, so it is refused when a manifest or a roster is loaded and when a token is built.

## Verification (run by me, Windows 10, Python 3.14)
- field-core tests/test_non_finite_limits_sa4.py: 20 passed. delegation-authority tests/test_doa_roster.py: 29 passed (116 s), including the new test that a roster row with `.inf`, `-.inf`, `.nan` or `1.0e999` gives a 503 "refusing to mint" with no token and no ledger event, and that a finite `1e12` still mints.
- Mutants (mine, 5 hand mutants, one at a time against those two files; files restored, both scratch worktrees clean afterwards). Counted from the output: 4 RED, 1 SURVIVED.
  - RED: `allow_inf_nan=False` removed from `DelegationToken.max_spend_usd`; removed from `SpendCap.limit`; removed from `GrantorRow.max_spend_usd`; `SpendCap.limit` `gt=0` weakened to `ge=0` (a zero cap).
  - SURVIVED: `ge=0` removed from `DelegationToken.max_spend_usd` (a negative stored ceiling). That bound pre-dates this PR and is not in its scope; it is simply not pinned by either file.

## Condition
**C1 (MEDIUM-LOW, confirmed by running): a token already stored with an infinite ceiling now breaks `/health` and `GET /tokens` of delegation-authority.**
`DelegationToken` is rebuilt from the database on every read (`TokenStore._row_to_token`), and the ceiling is a REAL column in a side table (`token_spend_ceilings`), which holds `+inf` happily. Before this PR a roster row `max_spend_usd: .inf` (a natural way to write "no cap") loaded, minted and stored such a ceiling. I inserted one row exactly as the old code would have written it and ran the app on the head (delegation-authority `create_app(store=...)`, TestClient): `GET /health` is 500 (it computes `token_count=len(_store().list())`), `GET /tokens` is 500, `GET /tokens?agent_id=<that agent>` is 500 (all `ValidationError`), while `GET /tokens?agent_id=<another agent>` is 200 and `store.get` of other tokens works. On current main the same three requests are all 200. One such row therefore takes the service's health endpoint down, which also fails a compose or Fly health check on deploy.
Whether any estate holds such a row is not in the repository (the roster and token databases are estate data; the shipped example roster uses 500.0 and the generator leaves the cap unset). The risk is small but the failure is severe and sudden.
Fix, pick one: (a) read side, treat a non-finite stored ceiling as "no ceiling" in `_row_to_token` (the same effective meaning it had, since an infinite cap never trips), with a test using a stored `+inf` row; or (b) a pre-deploy check in the runbook and a read-only query for non-finite values in `token_spend_ceilings` on each estate. Either way add the stored-row case to the tests, because the PR's tests only cover new input.

## Optional (LOW)
1. Rebase on current main before merge (base `cd3b7690`).
2. Pin `DelegationToken.max_spend_usd` `ge=0` (the surviving mutant).
3. The builder reports the renew-token R.unregistered step failed once in CI at this head and passed on re-run, root cause not found (comms/inbox/coordinator/20261106-0100-builder-pr502-green-and-pr537-correction.md); code the PR does not touch.

## Not covered
GX10 16 of 16 on the current head (a verifier ran one earlier: comms/inbox/coordinator/20261104-1211-gx10-verifier-2-pr502-full-16-suite.md, for an earlier head); CI; the whole delegation-authority and field-core suites; any estate's roster or token data (not in the repo); Linux.
