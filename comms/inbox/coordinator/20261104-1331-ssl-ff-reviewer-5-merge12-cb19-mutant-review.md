# Reviewer report: MERGE 12 fallback review (batch cb19, main 74131762 -> b5826200), reviewer ssl-ff-reviewer-5

READ-ONLY, after the fact (merged). **Head reviewed: b58262000c73e0df802f24693b382d438ce0a205** (28 commits, 25 files, +1694/-120: GuardedOperatorAuth and route tables in field-core, the lifecycle-manager PerRequestAuthClient and CLI guard, the kill-switch CLI client, ADR 10 notes, the proxy-env lint tests). Run UNVERIFIED (cloud, no GX10). Lane A C-1141 audited counts only; this is the first mutant review I know of for this batch (I did not find another in the files I read; not in source otherwise).

**VERDICT: PASS WITH CONDITIONS (retroactive).** No code defect found; the security-critical mechanisms are well pinned. Conditions are about what is NOT pinned (below). Main has since moved (MERGE 13 to 24); my results are for the batch head, not for current main.

## Objections first
1. `GuardedOperatorAuth` is copied, not shared: the lifecycle CLI has its own class (lifecycle_manager/cli.py:160) beside the field-core class and the kill-switch subclass (kill_switch/cli.py:132). Three copies of a credential rule drift; the pins are per copy, and I mutated all three. MEDIUM.
2. The mechanism protects only if the client never follows a redirect and never reads the proxy environment; that lives in each client's constructor, outside the auth class (stated in guarded_operator.py:21-26). A new client that forgets it has the pair on a redirect. The tests pin the three existing clients only. MEDIUM.
3. Route tables are hand-written lists; the drift test compares them to the receiver's own routes in both directions, which is good, but a receiver that guards a route another way is caught only through DECLARED_EXTRAS (hand-maintained). LOW-MEDIUM.
4. `git log` identity: all 28 commits author and committer = Don Hagell <13129187+dhagell@users.noreply.github.com>. HIGH.

## Mutants (real code lines, scratch worktree detached at b5826200, relative PYTHONPATH)
Stage order: field-core tests (1540 passed baseline), kill-switch and the three other c511 route tests, lifecycle-manager tests (264 passed). Baseline unmutated: 0 failed in every stage, so a fail is a kill. "Killed by" names the first stage that failed.
| group | behaviour | mutants | killed | survived |
|---|---|---|---|---|
| 1 | origin check in GuardedOperatorAuth (scheme, host, port ignored; always true) guarded_operator.py:99-101 | 4 | 4 | 0 |
| 2 | base-path prefix (no slash required, not stripped, outside prefix guarded, rstrip dropped) :84-89 | 4 | 3 | 1 (2a) |
| 3 | route matching (fullmatch->match, method ignored, `{name}` spans slashes, template upper-case, a guarded route dropped from a table) :44,79 | 5 | 4 | 1 (3d) |
| 4 | request_headers / perimeter_headers (guarded gets perimeter only, every request gets the pair, perimeter empty, perimeter without secret check) :117-122,111-114 | 4 | 4 | 0 |
| 5 | PerRequestAuthClient (send follows redirects, trust_env True, ctor follow_redirects True, foreign origin gets perimeter, outside base path gets the pair on a guarded route, raw string instead of wire URL) api.py:118-160 | 6 | 6 | 0 |
| 6 | wire-path decision in clients.py:254-259 (check dropped, own_client guard dropped, always refused) | 3 | 3 | 0 |
| 7 | drift_problems four reports and the guard-name test :144-153 | 5 | 5 | 0 |
| 8 | CLI clients: kill-switch and lifecycle follow redirects; lifecycle CLI copy of the origin check (scheme, host, port ignored, always true, pair check dropped) | 7 | 7 | 0 |
Totals COUNTED FROM THE TABLE: 4+4+5+4+6+3+5+7 = 38 mutants applied; 36 killed, 2 survived.
Survivors: 2a (`startswith(prefix)` instead of `startswith(prefix + "/")`, guarded_operator.py:86) and 3d (`m.upper()` removed in compile_routes, :44). Both are EQUIVALENT in practice, by reasoning and not by an executed proof: for 3d every template is a literal upper-case verb (lines 50-61), so `.upper()` changes nothing; for 2a a path that starts with the prefix but not the prefix and a slash leaves a remainder with no leading slash, and every route pattern starts with a slash, so `fullmatch` still fails. So 36 killed of 36 non-equivalent mutants; the equivalence of 2a and 3d is MEDIUM confidence.
Two earlier rows did not count: 5e was a weak mutant (the substitute route `/x` is not guarded, so no behaviour changed); it was replaced by 5e2 (a guarded route, killed) and the table above counts 5e2, not 5e. The placeholder 8c row was never applied and is replaced by the five CLI-copy rows.

## Findings
- F-M12-1 LOW: redirect and proxy-environment behaviour is pinned only for the three existing client classes (objection 2). A reviewer should check any new client that carries the pair; a repo-wide lint exists (the proxy-env lint tests in this batch) but I did not mutate it.
- F-M12-2 LOW: the guard is copied three times (objection 1); a shared import would remove two sets of pins. Not a defect.
- I did not mutate the ADR 10 docs, the symbol-pin test (test_adr10_note_symbols_c1026.py), the proxy-env lint (test_http_env_proxy_lint_c57.py, +438 lines) or clients.py beyond the wire-path lines; I did not read their prose claims against the code.

## Conditions
1. None block. Optional: a follow-up PR to share the guard class (F-M12-2) or pin the redirect rule at the class level.
