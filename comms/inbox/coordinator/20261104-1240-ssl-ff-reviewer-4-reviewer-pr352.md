# Reviewer report: PR 352 @ 6f3065793aa7dceb345ed746e7568036062d0e08 (C-582, C-623: force-gateway names the variable never the value; sentinel URL shown as origin only)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Base 5808a5cd (old); 5 commits; 3 files (+272/-21): force_gateway/api.py, tests/test_no_value_echo_c582.py (+203), docs/ENVIRONMENT.md.

## Objections first (two are blocking as it stands)
1. IDENTITY (HIGH, run by me): commit 3a525dcc "force-gateway tests: the unreachable-sentinel 503 body carries no credentialed URL" has author AND committer `Claude <noreply@anthropic.com>`, not the Don Hagell noreply identity (`git show -s --format='%an <%ae> | %cn <%ce>' 3a525dcc`). The repository is public and history is never rewritten by a lane; the coordinator's PR 381 ruling allows re-authoring a commit INSIDE a batch branch only (cherry-pick --reset-author, patch-id identical). The other 4 commits are Don Hagell 13129187+dhagell@users.noreply.github.com with Sonnet 5.5 trailers.
2. MERGE (HIGH, run by me): `git merge-tree --write-tree origin/main pr352` reports a 3-way CONFLICT in docs/ENVIRONMENT.md. Per the coordinator's rule after MERGE 14, resolve by rebasing and running `python tools/environment_anchors.py --fix` then `--check`, not by hand-merging rows.
3. The PR's claim is a negative ("never echoes the value"); tests that only inspect a few channels (exception text, caplog, /health, 503 body) can miss a channel; the mutants below try to open each one.

## Verified
- Baseline on the exact head: tests/test_no_value_echo_c582.py 83 passed (relative PYTHONPATH `../../packages/field-core/src:../../packages/field-agent/src:src`).
- Code read: `_env_number` raises `InvalidNumericSetting` OUTSIDE the except block (no chained original text) naming the variable and the expected form only; `public_origin` keeps scheme, host, port, refuses non-http(s), junk hosts and IPv6 scope ids with the fixed word "(unparsable url)"; `SentinelClient` raises `SentinelUnavailable` outside the handler with the exception TYPE only and the origin only; `/health` shows `public_origin(sentinel_url)`.

## Mutants (scratch worktree on the head; baseline 83 passed; kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| N1 | _env_number echoes the original error | 40 failed | yes |
| N2 | message carries the value | 5 failed | yes |
| N3 | message drops the variable name | 40 failed | yes |
| N4 | ignores the default | 1 failed | yes |
| N5 | float case says "an integer" | 2 failed | yes |
| N6 | FORCE_HYGIENE_WINDOW back to raw int/float | 8 failed | yes |
| N7 | FORCE_GATEWAY_LATENCY_BUDGET_MS raw | 8 failed | yes |
| N8 | FORCE_GATEWAY_BYPASS_COOLDOWN raw | 8 failed | yes |
| N9 | FORCE_HYGIENE_BAND raw | 8 failed | yes |
| N10 | FORCE_HYGIENE_BASELINE_WINDOWS raw | 8 failed | yes |
| O1 | public_origin keeps userinfo | 5 failed | yes |
| O2 | keeps the path | 5 failed | yes |
| O3 | drops the port | 10 failed | yes |
| O4 | IPv6 brackets dropped | 1 failed | yes |
| O5 | any scheme allowed | 2 failed | yes |
| O6 | junk host shown | 22 failed | yes |
| O7 | unparsable URL echoed | 2 failed | yes |
| O8 | empty URL shown as the fixed word | 9 failed | yes |
| H1 | scope id accepted | 6 failed | yes |
| H2 | hostname edge-character rule removed | 9 failed | yes |
| H3 | underscore refused | 2 failed | yes |
| H4 | IP literals refused | 1 failed | yes |
| H5 | every non-hostname accepted | 14 failed | yes |
| S2 | 503 text names the full base URL | 16 failed | yes |
| S3 | 503 text drops the exception type | 1 failed | yes |
| S4 | 503 text includes the exception text | 16 failed | yes |
| S5 | /health shows the full URL | 14 failed | yes |
Totals counted from the table: 27 mutants, 27 killed, 0 survived (10 on the numeric tunables, 8 on public_origin, 5 on _is_host, 4 on the 503/health channels). My mutant for "re-chain the cause with `from exc`" did not build in a form I trust and is excluded; the non-chaining itself is pinned by test_the_transport_error_is_not_chained_c734 (not independently mutated by me). Not run: the other force-gateway tests and the other suites.

## Findings
- F-C582-1 PROCESS (blocking merge as-is): objection 1; needs a coordinator-side re-author inside the batch (patch-id identical), not a push to this head.
- F-C582-2 PROCESS (blocking merge as-is): objection 2, rebuild on current main with environment_anchors `--fix` and `--check`; the rebuilt head needs a re-check of the changed ENVIRONMENT.md rows (I have not seen it).
- F-C582-3 LOW: non-chaining is pinned by one test I did not mutate.

## Verdict: PASS WITH CONDITIONS on 6f3065793aa7dceb345ed746e7568036062d0e08 (content PASS; merge blocked on F-C582-1 and F-C582-2)
Conditions: (1) commit 3a525dcc re-authored inside the batch only; (2) rebuild on current main with the ENVIRONMENT.md conflict resolved by environment_anchors; (3) CI green and GX10 16/16 on the rebuilt head. Not run by me: CI, GX10, the rebuilt head.
