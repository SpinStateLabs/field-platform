# Lane O reviewer: batch cb7 = MERGE 4 (main 6a37ae76 to b152e955; PRs 349, 363, 373, 375; 21 commits), read-only re-audit of the merged code. PARTIAL. UNVERIFIED (cloud, no GX10)

VERDICT: PASS WITH CONDITIONS (retroactive; already on main) for the CODE parts I covered, naming the merged head b152e955: PR 349 delegation-authority revoke (api.py, store.py), PR 375 field-core verifier-row rules (operator_auth.py), PR 373 spend-governor /totals (api.py). NOT COVERED, "I do not know": PR 363 (docs/VIDEO-SCRIPT.md, tools/tests/test_video_script_c590.py, docs/runbooks/v1.2-deploy-rollback.md) and the small tools test edits; no verdict on those. All 21 commits: Don Hagell noreply as author and committer (git log of 6a37ae76..b152e955, HIGH). Claimed through dispatch.sh (R-BATCH-cb7). No earlier reviewer file names cb7 as a batch; STATUS MERGE 4 cites per-PR reviewer PASS, which I did not re-read.

Objections first: (1) revoke ordering is ledger-first, so a `delegation.revoke` event can exist while the token still introspects active (crash window); the code and README now say "revoke REQUESTED" (read, HIGH). A consumer that reads the ledger event as "revoked" is wrong in that window; no sweep finishes it (the code says so). (2) the revocation id is now deterministic (uuid5 of the token id): it is stable on retry, but anyone who knows a token id can compute its revocation id; fine if that id is not a capability (I did not find it used as one; MEDIUM). (3) the per-token lock is per process; across processes safety rests on the conditional UPDATE (`AND revoked=0`), which the tests cover with a two-process race.

Run here (cloud, scratch worktree on b152e955, relative PYTHONPATH of every service src and packages src): delegation-authority new file test_revoke_c625.py 30 passed, whole delegation-authority suite 243 passed; field-core test_delegation_pins_c625.py plus test_verifier_prefix_c805.py 79 passed, and with test_operator_auth_format2.py and test_operator_auth_machine_verifier.py 198 passed; spend-governor test_reaudit_c616.py 43 passed. NOT run: the 16-suite set, CI.

Mutants (82 run in two groups, scratch worktree; each against the PR's own test file(s), survivors against the whole service or package suite; the unmutated baseline of every suite used for the survivor check passes, so no kill is a baseline failure):
Group A, PR 349 revoke (45 mutants):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 ledger down: 502 and the token stays active | 5 | 4 | 1 |
| B2 retry after the ledger is back succeeds | 4 | 4 | 0 |
| B3 concurrent revokes: one id, one event | 4 | 4 | 0 |
| B4 second revoke returns the first id, no second event | 4 | 4 | 0 |
| B5 unknown token: 404, nothing written | 3 | 1 | 2 |
| B6 ledger error answer is a refusal naming the status only | 4 | 4 | 0 |
| B7 unreachable ledger still says unreachable | 4 | 3 | 1 |
| B8 save_revoked once; the loser gets the winner's row | 4 | 3 | 1 |
| B9 padded token id is unknown; blank is 400 | 4 | 4 | 0 |
| B10 revocation id is a function of the token id | 4 | 2 | 2 |
| B11 keyed locks: exclude one key, not two, dropped when idle | 5 | 4 | 1 |
| Subtotal (counted from the rows) | 45 | 37 | 8 |
Group B, PRs 375 and 373 (37 mutants):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 verifier scope set without the svc-verifier- prefix is refused | 5 | 5 | 0 |
| B2 a prefixed row holding bypass_operator_list is refused | 4 | 4 | 0 |
| B3 a non-list scopes value never raises | 4 | 3 | 1 |
| B4 an inactive row is exempt | 4 | 4 | 0 |
| B5 a row holding "*" is exempt | 4 | 4 | 0 |
| B6 the prefix is matched exactly | 4 | 4 | 0 |
| B7 /totals: an overflowing instant is 422 | 4 | 4 | 0 |
| B8 /totals: the 422 never repeats the caller's text | 4 | 3 | 1 |
| B9 /totals: a naive instant is read as UTC | 4 | 4 | 0 |
| Subtotal (counted from the rows) | 37 | 35 | 2 |
Total A + B (counted): 82 mutants, 72 killed, 10 survived.

Survivors (10): 6 equivalent or non-informative: dead code after a return (B1 A); the inner "token not found" re-check under the lock, reachable only if a token is deleted between two reads and nothing deletes tokens (B5, 2, MEDIUM); COALESCE(revocation_id, ?) under `AND revoked=0` (revocation_id is null there, B8); dropping `from None` on the 422 (exception chaining only, B8 of group B); `scopes = r["scopes"]` (a row without scopes cannot reach this function through the loader: not proven, MEDIUM). 4 real LOW pin gaps:
- F-O-cb7-1: the unreachable-ledger message loses its detail `: {exc}` unnoticed (B7).
- F-O-cb7-2: no known-answer test of the revocation id derivation: uuid5 over the token id alone and over a fixed string both survive; a change of derivation would give a different id on retry across a deploy (B10, 2).
- F-O-cb7-3: the keyed lock count with three contenders: decrementing by 2 and popping at <= 0 survives; with two waiters the entry is dropped while one still holds it, so a third arrival gets a new lock and two holders run (B11). Real, LOW-MEDIUM.

CONDITIONS (none blocking; the batch is on main): C1 a tests-only card for F-O-cb7-1..3. C2 an assignment for PR 363 (VIDEO-SCRIPT, runbook, video-script pin test): not reviewed here; do not read this report as covering it.

Tokens/cost line: not available to me. I do not know.
