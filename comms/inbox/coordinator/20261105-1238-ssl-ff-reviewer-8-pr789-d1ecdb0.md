# Review PR 789 (S8-31 force-gateway: validate drift and bypass tuning variables at start) by ssl-ff-reviewer-8

VERDICT: **PASS** on head `d1ecdb0b8e5e38a74683f3c426c6354fe4a2009a`.

## Checks (HIGH unless noted)
- Head = d1ecdb0b8e5e38a74683f3c426c6354fe4a2009a (`gh pr view`, fetched refs/pull/789/head). Files: docs/ENVIRONMENT.md (11 rows), force_gateway/api.py, drift.py, tests/test_tuning_env_bounds.py (new). Nothing under .github/ or comms/. All commits in `main..head` are author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>.
- `python tools/environment_anchors.py --check` on the head: 0 wrong anchor rows.
- Logic read: `_env_number` strips, blank = default, parse failure / non-finite / out of bounds -> ValueError naming the variable, never the value; refuse, not clamp. Bounds match the ENVIRONMENT.md rows (window >= 1, baseline >= 1, band finite >= 0, latency finite > 0, cooldown 0..1,000,000). `DriftTracker` refuses window < 1, baseline < 1, non-finite or negative band. Explicit `create_app(latency_budget_ms=..., bypass_cooldown=...)` arguments stay unvalidated (existing d2 test passes -1.0 on purpose); pinned by a test.
- Shipped defaults: the five variables appear only commented out in `.env.example` (lines 148-152) at their default values; no compose/fly file sets them in the head tree (git grep). So no shipped config is refused. Estate env files are not visible to me (not in source).
- Tests on the head (Windows, Py3.14, field-core on path): new file 83 passed. The PR's "force-gateway 531 passed" I did not reproduce (the suite is slow here); not verified by me.

## Mutants (17; table counted)
| # | mutant | result |
|---|---|---|
| 1 | blank no longer the default | killed |
| 2 | no strip | killed |
| 3 | window minimum 0 | killed |
| 4 | baseline minimum 0 | killed |
| 5 | band minimum -1 | killed |
| 6 | latency budget not exclusive of 0 | killed |
| 7 | cooldown no maximum | killed |
| 8 | cooldown minimum 1 (rejects 0) | killed |
| 9 | finite check removed | killed |
| 10 | clamp to minimum instead of refusing | killed |
| 11 | message carries the raw value | killed |
| 12 | maximum off by one (>=) | killed |
| 13 | DriftTracker window check dropped | killed |
| 14 | DriftTracker baseline check dropped | killed |
| 15 | DriftTracker finite check dropped | killed |
| 16 | DriftTracker band `>= 0` -> `> 0` | killed |
| 17 | DriftTracker non-negative check dropped | killed |
Totals from the table: 17 mutants, 17 killed, 0 survived.

## Notes (LOW, optional, new PR only)
- Decision for Don, as the PR says: the 1,000,000 cooldown ceiling; and a deploy-time refusal for an estate that currently sets e.g. `FORCE_GATEWAY_LATENCY_BUDGET_MS=0` (not visible to me).
- No upper bound on window or baseline windows, and none on band (a band above 1 can never alert since scores are presumably 0..1: not verified). Python's `float("1_0")`/`int("1_0")` accept underscores.
- The "never the value" assertion in the test is partly weakened by `or len(bad) <= 3` and a blanket skip for "0"/"-1"; mutant 11 was still killed.
- Rebase on current main not run.
