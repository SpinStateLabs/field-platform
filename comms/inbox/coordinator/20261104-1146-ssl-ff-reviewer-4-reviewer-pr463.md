# Reviewer report: PR 463 @ c0f781d4320d079c6836d63cd4e125566b3147e9 (C-1181 part 1, C-1150 F2 slice C)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Base 6385f877; two commits (b8656e20 code+test, c0f781d4 ENVIRONMENT.md anchors); both author and committer = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). No estate address, flag value, build id or deploy status in the diff (HIGH).

## Objections first
1. Swapping `auth_headers()` for `perimeter_headers()` is only safe if every route these ten sites call is unguarded; one guarded write sent without the pair would turn into a 401/403 at runtime, and unit tests with mocked httpx cannot see that.
2. Seven of the ten sites are pinned only by an AST "no call named auth_headers" test; the two crosswalk sites and the force-gateway `serve` governor client have no behavioural test, and an aliased import defeats the AST check.
3. The PR is on 6385f877, main is now 97dcfec1 (ENVIRONMENT.md anchors moved by cd3b7690); a rebase may need `environment_anchors.py --fix`.

## Verified
- Route safety (objection 1), read on the head: spend-governor guards only `caps` and `escalation` (services/spend-governor/src/spend_governor/api.py:283-284); force-gateway calls the governor on `/usage`, `/spend`, `/status/...` (force_gateway/api.py:517,523,674,699), none guarded; sentinel `POST /check` (api.py:362) has no op_health.guard in sentinel (grep, MEDIUM: absence of a match); incident-replay reads ledger `/events` and delegation `/tokens`; attestation engine only `client.get` (engine.py:151); crosswalk reads ledger `/events`. `perimeter_headers()` = secret only (field_core/guarded_operator.py:111-114) (HIGH). I did not run a live call.
- Head unchanged at c0f781d4; `tools/tests/test_perimeter_only_clients_c1181.py`: baseline 12 passed (after installing cryptography into my scratch venv; without it test_attestation_reporter_engine_clients fails on import, an environment gap, not counted).
- `python tools/environment_anchors.py --check` on the head: 0 wrong anchor rows. Merge into current main 97dcfec1 (`git merge-tree --write-tree`): clean tree, no conflict.

## Mutants (scratch worktree on the head, relative PYTHONPATH, baseline 12 passed subtracted: a kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| M1 | replay engine LedgerQueryClient -> auth_headers | 2 failed | yes |
| M2 | replay engine TokenQueryClient -> auth_headers | 2 failed | yes |
| M3 | replay cli markdown post -> auth_headers | 2 failed | yes |
| M4 | replay cli plain post -> auth_headers | 2 failed | yes |
| M5 | gateway SentinelClient -> auth_headers | 2 failed | yes |
| M6 | gateway cli telemetry -> auth_headers | 2 failed | yes |
| M7 | gateway cli serve governor client -> auth_headers | 1 failed (AST test only) | yes |
| M8 | attestation engine_from_env -> auth_headers | 2 failed | yes |
| M9 | crosswalk api _get -> auth_headers | 1 failed (AST test only) | yes |
| M10 | crosswalk cli suggest -> auth_headers | 1 failed (AST test only) | yes |
| M11 | replay engine ledger client headers = {} (secret dropped) | 1 failed | yes |
| M12 | attestation headers = {} (secret dropped) | 1 failed | yes |
| M13 | crosswalk api: `auth_headers as perimeter_headers` alias | 12 passed | NO |
| M14 | gateway cli alias (telemetry + serve) | 1 failed (telemetry behaviour test) | yes |
| M15 | replay engine alias (both query clients) | 1 failed | yes |

Totals counted from the table: 15 mutants, 14 killed, 1 survived (M13). Survivor M13 run against the whole compliance-crosswalk service suite (368 passed, 1 failed, 5 skipped; the 1 failure test_regwatch::test_serve_reads_every_from_flag_and_env is identical on the unmutated head, a missing module, so not a kill): still survives. I did not run all 16 suites.

## Findings
- F-C1181-1 LOW: crosswalk api.py `_get` (live-platform branch) and cli.py suggest have no behavioural test; the AST pin does not catch an alias import (M13). Optional follow-up: one test that monkeypatches `httpx.get` for `collect_evidence`/`suggest`.
- F-C1181-2 LOW: stale docstrings still say `auth_headers()`: services/force-gateway/src/force_gateway/api.py:31 and :343; attestation-reporter api.py engine_from_env docstring ("``auth_headers()`` attached"). Wording only.
- F-C1181-3 LOW: the ten sites are "part 1"; other sites still use auth_headers() (e.g. spend-governor cli.py, sealed-ledger cli.py:610 and witness.py:154, claude-approver core.py:219). Not in this PR's claim; I did not judge whether those are guarded writes.

## Verdict: PASS on c0f781d4320d079c6836d63cd4e125566b3147e9 (conditions below are procedural)
Conditions (coordinator): CI green and GX10 16/16 on this exact head rebased on current main; run `python tools/environment_anchors.py --fix` then `--check` after the rebase; head frozen after this PASS, LOWs go in a NEW PR. Not run by me: CI, GX10, a live request.
