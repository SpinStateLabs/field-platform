# Reviewer report (fallback, read-only): MERGE 4 (batch cb7: PRs 349, 363, 373, 375; 21 commits) on current main ebb027a2

Reviewer: ssl-ff-reviewer-6 (cloud, NO GX10; UNVERIFIED). Fallback of the role loop: `dispatch.sh next reviewer` is still EMPTY (restock-needed-3 filed; re-checked after each fallback). Nothing was pushed; I changed no repository file. Commits listed by `git log 6a37ae76..b152e955`: every author and committer reads "Don Hagell" (HIGH for the names; I did not check each email field).

Scope (code only): (1) field-core `operator_auth.validate_rows`: the machine-verifier scope rules (C-805 Don ruling D-18, C-1003); (2) delegation-authority revoke: stable revocation id, per-token lock, conditional write, ledger-first (C-625, C-725, C-821); (3) spend-governor `/totals` `since` handling (C-616, C-856). Not reviewed: the VIDEO-SCRIPT docs and the video-script figure pin (tools/tests/test_video_script_c590.py), the runbook and README lines.

## Verdict: PASS (merged code and tests on ebb027a2). Retrospective: no merge condition.

## Objections first (FORCE-O)
1. The verifier rule is a deny rule on scope SHAPES, not on identities: it refuses an active row that holds `kill`, `revive`, `revoke` and (`mint` or `mint_for_others`), has no `*`, and whose id lacks the exact `svc-verifier-` prefix. A row that holds the same power through a different combination of scopes (for example without `revoke`) is not refused. That is the ruling's text (D-18) as written in the code comment; I did not compare it to the ruling document (not verified). The 14 mutants of the rule's parts (each core scope, each mint alternative, `*`, status, prefix case, all-versus-any) are all killed, so the rule is exactly what the tests say it is.
2. The revoke path's guarantee is stated in the code as "at least one `delegation.revoke` event, at most one revocation id per token, the same id every attempt", and `delegation.revoke` means "revoke REQUESTED": between the ledger append and the store write the token still introspects active, and a crash there leaves it unrevoked until a retry. No sweep finishes it (named out of scope in the comment). That is a real window for a kill-type operation; it is disclosed, not a defect (HIGH, from the comment at api.py in the revoke handler).
3. The per-token lock is in-process only: a second process can still write a repeat event with the same id (stated). The conditional write (`WHERE revoked=0`, Y1 killed) is what makes the stored row single; Y2 (returning the loser's own object instead of the stored row) is also killed.
4. The locks are created and dropped by a counter (X13, X14 killed), so memory is bounded by revokes in flight; X4 (one global lock) is killed, so independence of two tokens' revokes is pinned.
Steelman: before these commits a retried or raced revoke could mint two revocation ids and two ledger events for one token, a padded token id was trimmed on `/oauth/introspect` where `/introspect` matched exactly, `/totals` answered 500 on an instant whose UTC form overflowed and quoted the caller's text in its 422, and a machine-verifier-grade row under a different id spelling escaped the list-bound rules.

## Runs on main ebb027a2 (UNVERIFIED, PYTHONDONTWRITEBYTECODE=1, absolute PYTHONPATH)
- field-core test_verifier_prefix_c805.py: 62 passed. delegation-authority test_revoke_c625.py: 30 passed. spend-governor test_reaudit_c616.py: 43 passed.

## Mutants (kill = the merge's own test file; baselines 62, 30, 43)
| group | ids | result |
|---|---|---|
| operator_auth verifier rules (62 tests) | W1 kill dropped from the set, W2 revoke dropped, W3 only `mint`, W4 only `mint_for_others`, W5 `*` rows not exempt, W6 status check dropped, W7 prefix not required, W8 any-of instead of all-of, W9 bypass check on inactive rows, W10 bypass check on any id, W11 bypass check removed, W12 unprefixed check removed, W13 non-list guard removed, W14 prefix compared case-insensitively | all 14 KILLED |
| delegation-authority api.py (30 tests) | X1 random revocation id, X2 constant id, X3 lock removed, X4 one global lock, X5 already revoked re-appends, X6 token not re-read under the lock, X7 `save` instead of `save_revoked`, X8 ledger status refusal not distinguished, X9 refusal text echoes the ledger body, X10 store written before the ledger, X11 introspect token id trimmed, X12 blank token not a 400, X13 lock entries never dropped, X14 lock count not incremented | all 14 KILLED |
| delegation-authority store.py | Y1 conditional update dropped, Y2 loser gets its own object | both KILLED |
| spend-governor api.py (43 tests) | Z1 OverflowError not caught, Z2 ValueError not caught, Z3 422 echoes the value, Z4 naive instant not UTC, Z5 status 400 | all 5 KILLED |
Total 35 counted from the table; 35 killed; no survivors; no equivalent mutants identified.
