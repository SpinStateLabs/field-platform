# Reviewer report: PR 425 @ 186998a7a72e8d724c0f4e7b4b9c682a3b50366d (C-1098, stacked on PR 344)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Scope reviewed: the two commits that are this PR's own (13f437d4 `--cacert` code + tests; 186998a7 docs). The four older commits (484b36cf, 85a5eb08, f813e9bc, 3038498f) are the PR 344 stack (C-575, Don's HOLD) and are NOT reviewed here; PR 344's head 22d04601 is not an ancestor of this head (the stack was rebuilt), so this review does not cover 344. Author and committer of all six commits = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH).

## Objections first
1. Cannot land as-is: it is stacked on a PR Don ruled HOLD, built on base 9468b184, and `git merge-tree --write-tree origin/main pr425` reports a 3-way CONFLICT in services/lifecycle-manager/src/lifecycle_manager/cli.py (HIGH). Main's cli.py `_service_client` has no `trust_env`/`verify` yet (origin/main cli.py:197), so the C-575 base this builds on is not on main.
2. Process: commits 13f437d4 and 186998a7 carry `Co-Authored-By: Claude Fable 5.1`; the standing rule for every lane is Opus/Sonnet/Haiku, never Fable (HIGH that the trailer is present; MEDIUM that a Fable session wrote them). The other four commits carry Sonnet 5.5.
3. A security option (TLS trust) whose claim "the bundle REPLACES the trust store" is not pinned (V9 below).

## Verified
- Baselines on the exact head: test_cli_cacert_c1098.py 10 passed; with test_cli_clients_no_proxy_c575.py and tools/tests/test_http_env_proxy_lint_c57.py 72 passed; whole services/lifecycle-manager/tests 294 passed, 2 failed (the same 2 on every run, environment, never counted as kills).
- Code read: `_verify_from` returns True without the option, `ssl.create_default_context(cafile=...)` with it (trust only that bundle), refuses a non-PEM file with exit 2 and the exception class only, never `False`; `estate_clients` passes `verify` to all five clients; `sweep`, `provision`, `decommission` take `--cacert`.
- Docs (186998a7): README and runbook text match the code (trust_env stays False, SSL_CERT_FILE unread, no switch turns verification off). A pre-existing context line in the runbook (v1.2-deploy-rollback.md, the httpx bullet) holds a personal home-directory path; not added by this PR.

## Mutants (scratch worktree on the head; baseline 10 passed in the cacert file; kill = at least one failure)
| # | Mutant (cli.py) | Result | Killed |
|---|---|---|---|
| V1 | verify= dropped from the client | 2 failed | yes |
| V2 | _verify_from(None) returns False | 4 failed | yes |
| V3 | trust_env=True | 2 failed | yes |
| V4 | sweep ignores --cacert | 2 failed | yes |
| V5 | _provision_clients ignores the bundle | 3 failed | yes |
| V6 | non-PEM bundle swallowed | 1 failed | yes |
| V7 | provision passes None | 1 failed | yes |
| V9 | bundle ADDS to the store instead of replacing | 10 passed | NO |
| V10 | refusal echoes the path | 1 failed | yes |
| V11 | refusal echoes the exception text | 10 passed | NO |
| V13 | hostname check off | 1 failed | yes |
| V14 | verify_mode CERT_NONE | 2 failed | yes |
| V15 | governor client misses verify | 1 failed | yes |
| V16 | killswitch client misses verify | 1 failed | yes |
| V17 | delegation client misses verify | 1 failed | yes |
| V18 | ledger client misses verify | 1 failed | yes |
| V19 | _service_client default verify -> False | 2 failed | yes |
| V20 | estate_clients default verify -> False | 1 failed | yes |
| V21 | decommission passes None | 1 failed | yes |
Totals counted from the table: 19 mutants, 17 killed, 2 survived (V9, V11). Both survivors run against the whole lifecycle-manager suite plus the two sibling files: V9 2 failed, 294 passed; V11 2 failed, 294 passed; baseline is also 2 failed, 294 passed, so neither is killed. The earlier-claimed hand mutants V1-V6 in the commit message are reproduced as kills.

## Findings
- F-C1098-1 MEDIUM: V9, the "replaces, does not add" trust claim (README, runbook, docstring) has no test: with the system store added to the bundle every test still passes. Add a case where a leaf signed by a CA in the system store (or a second throwaway CA loaded via a patched default context) is refused under `--cacert`.
- F-C1098-2 LOW: V11 equivalent in practice (`exists=True` rejects a missing path first; an SSLError text for a non-PEM file carries no path); a one-line test with a permission-denied file would pin it.
- F-C1098-3 PROCESS: Fable trailer on 13f437d4 and 186998a7 (objection 2). Coordinator ruling needed; I cannot rewrite history and did not.
- F-C1098-4 PROCESS: unmergeable until PR 344's rebuild lands on current main and this is re-stacked; PR 344's own review is a separate item.

## Verdict: PASS WITH CONDITIONS on 186998a7a72e8d724c0f4e7b4b9c682a3b50366d (for the two own commits only)
Conditions: (1) PR 344 lands first (Don's HOLD) and this is rebuilt on current main with the cli.py conflict resolved; the rebuilt head needs its own check, I have not seen it; (2) F-C1098-1 fixed (a condition fix is the only push allowed) or ruled a follow-up in writing; (3) the Fable trailer ruled on by the coordinator; (4) CI green and GX10 16/16 on the rebuilt head. Not run by me: CI, GX10, the rebuilt head.
