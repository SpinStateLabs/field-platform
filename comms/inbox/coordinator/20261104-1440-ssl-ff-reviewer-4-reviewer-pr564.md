# Reviewer report: PR 564 @ 54f13c8a55e1d4992d0476f8cffe59dd3f6ba7ce (rebuild of #425: lifecycle-manager CLI --cacert, with the PR 344 / C-575 stack beneath it)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Six commits on origin/main 97dcfec1 (main is now b963407a): the C-575 stack (56441ccc, 7d16eeea, c0c44a07, 6c87a5c7) and the C-1098 pair (55b2b513 code and tests, 54f13c8a docs). 7 files (+701/-22): lifecycle_manager/cli.py (+65), api.py (3 lines), README, runbook, test_cli_cacert_c1098.py (+232), test_cli_clients_no_proxy_c575.py (+397), tools/tests/http_env_proxy_allowlist.txt. `git merge-tree --write-tree origin/main pr564` clean (HIGH): unlike old PR 425 (head 186998a7), this rebuild no longer conflicts in cli.py. Author and committer of all 6 = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). Trailers: 4 Sonnet 5.5, 2 Fable 5.1 (54f13c8a 55b2b513 ).

## Objections first
1. PROCESS: 2 of the 6 commits carry `Co-Authored-By: Claude Fable 5.1`; the standing rule for every lane is Opus/Sonnet/Haiku, never Fable (HIGH that the trailers are present; MEDIUM that a Fable session wrote them). Coordinator ruling needed.
2. This is a REBUILD, so my earlier report on the old head (PR 425 @ 186998a7: PASS WITH CONDITIONS, 17 of 19 killed) does not transfer. The last commit (54f13c8a) is patch-equal to old 186998a7 (patch-id 634d29cae4, run), the other five are rebased or changed (different patch-ids), so I re-ran everything on this head.
3. The old condition F-C1098-1 (the claim "the bundle REPLACES the trust store, it does not add to it" is unpinned) was a request for a test; the rebuild adds none: see V9.

## Verified (run by me)
- On the exact head the three suites (cacert and no-proxy tests plus the C-57 lint) show 1 failure, `test_the_repo_matches_the_allowlist`: tools/start_role_session.py (a site that main fixed afterwards in PR 546) is not on the allowlist at the head's base. On a scratch merge of this head with current main (clean, committed in a scratch worktree) the whole services/lifecycle-manager/tests plus tools/tests/test_http_env_proxy_lint_c57.py: 422 passed (HIGH). So the failure belongs to the base, not to this PR.
- The two lifecycle files (test_cli_cacert_c1098.py, test_cli_clients_no_proxy_c575.py): 51 passed on the head. Code read: `_service_client` builds `httpx.Client(..., trust_env=False, follow_redirects=False, verify=verify)`; `_verify_from` returns `True` without the option and `ssl.create_default_context(cafile=...)` with it; a non-PEM file is refused (exit 2) with the exception class only; `sweep`, `provision` and `decommission` take `--cacert`.

## Mutants (mutations of lifecycle_manager/cli.py; scratch worktree on the head; baseline 51 passed; kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| V1 | verify= dropped from the client | 2 failed | yes |
| V2 | _verify_from(None) returns False | 4 failed | yes |
| V3 | trust_env=True (also run as V23 with the same result, 35 failed) | 35 failed | yes |
| V4 | sweep ignores --cacert | 2 failed | yes |
| V5 | _provision_clients ignores the bundle | 3 failed | yes |
| V6 | non-PEM bundle swallowed | 1 failed | yes |
| V7 | provision passes None | 1 failed | yes |
| V9 | bundle ADDS to the system store instead of replacing it | 51 passed | NO |
| V10 | refusal echoes the path | 1 failed | yes |
| V11 | refusal echoes the exception text | 51 passed | NO |
| V13 | hostname check off | 1 failed | yes |
| V14 | verify_mode CERT_NONE | 2 failed | yes |
| V15 | governor client misses verify | 1 failed | yes |
| V16 | killswitch client misses verify | 1 failed | yes |
| V17 | delegation client misses verify | 1 failed | yes |
| V18 | ledger client misses verify | 1 failed | yes |
| V19 | _service_client default verify -> False | 2 failed | yes |
| V20 | estate_clients default verify -> False | 1 failed | yes |
| V21 | decommission passes None | 1 failed | yes |
| V22 | follow_redirects True | 24 failed | yes |
Totals counted from the table: 20 distinct mutants (V3 and V23 are the same change, counted once), 18 killed, 2 survived (V9, V11). V9 and V11 are the same two survivors as on the old head. Survivors against the whole lifecycle-manager suite: on the old head both survived the whole suite (294 passed) and the code under test is unchanged in these lines; on this head I ran the whole suite only on the scratch merge unmutated (422 passed), not per survivor. So treat them as surviving the two files that pin this change.

## Findings
- F-C1098-1 MEDIUM (carried from the old head, still open): V9, "replaces, does not add" is claimed in the README, the runbook and the docstring and pinned by no test.
- F-C1098-2 LOW: V11 is practically equivalent (the option has `exists=True`; an SSLError text for a non-PEM file holds no path); one test with a permission-denied file would pin it.
- F-C1098-3 PROCESS: Fable trailers (objection 1).
- F-C1098-4 note: the C-575 commits beneath are PR 344's content; I mutated only the proxy, redirect and verify lines they and the cacert change share (V3, V22, V23 killed), not every behaviour of the stack.

## Verdict: PASS WITH CONDITIONS on 54f13c8a55e1d4992d0476f8cffe59dd3f6ba7ce
Conditions: (1) coordinator ruling on the Fable trailers; (2) F-C1098-1 fixed on the PR (a condition fix is the only push allowed) or ruled a follow-up in writing; (3) Don's HOLD on the C-575 stack (PR 344) is a business decision, not mine: if it still holds this PR holds with it; (4) CI green and GX10 16/16 on this exact head rebased on current main. Not run by me: CI, GX10.
