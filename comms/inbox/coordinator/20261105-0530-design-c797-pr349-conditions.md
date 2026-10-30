VERDICT: C-797 PASS WITH CONDITIONS on 1e3dea5a7fac517757e31290e125652930d6568c (PR 349, was 50c87b9; full sha in the "Full head" line at the end). My C-701 conditions 1, 2 and 3 are closed and the guarantee is now stated as it holds. Condition 4 (introspection distinguishes unknown from revoked) is open and is a decision. A new property to decide: the revocation id is now derived from the token id. Cloud container, in-process test client, UNVERIFIED on any estate.

## Conditions of C-701 and state at this head (observed with the same probe, adapted)
1. Crash between ledger and store, then retry: was 2 events with 2 different ids; now 2 events, 1 distinct id, and the stored id is that id. CLOSED for the id; the repeat event remains by design ("at least once", stated in the api.py comment and the README row). HIGH.
2. Two processes revoking one token: was an event carrying an id no token stores; now both return the same id and the stored id equals the ledger's. CLOSED. HIGH.
3. One lock serialising revokes of different tokens (was 1.02 s and 2.03 s with a 1.0 s ledger): now 1.03 s and 1.03 s, parallel (`_KeyedLocks`, per token id, entries dropped when idle). CLOSED. HIGH.
4. `/introspect` distinguishes unknown from revoked: unchanged (unknown: "unknown token id — treated as revoked (fail closed)"; revoked: "token is revoked"). `/oauth/introspect` returns `{"active": false}` for both. OPEN, decision. Timing over 300 calls each (median, standard deviation): /introspect revoked 3.26 ms (0.72) and unknown 3.14 ms (0.80); /oauth revoked 2.98 ms (1.91) and unknown 3.07 ms (0.86): no timing difference visible at this resolution; the body differs on /introspect only. MEDIUM (timing measured with the in-process test client, not over a network).
5. Padded, upper-cased and newline-suffixed ids: exact match, unknown (unchanged). HIGH.

## Objections first
1. THE REVOCATION ID IS NOW A PUBLIC FUNCTION OF THE TOKEN ID. `stable_revocation_id` (api.py:128-134) is a version-5 UUID of the URL namespace and `field:delegation-revoke:<token_id>`. Anyone who knows a token id can compute the revocation id before the revoke happens, and two tokens never collide. If any consumer treats the revocation id as proof that a revoke happened (rather than as a label), it is forgeable; I found no such consumer: grep shows the id is stored (store.py:21, :78), written to the ledger event (api.py:~430) and read for display by incident-replay (engine.py:182, :428). MEDIUM (reasoned; consumers outside this repository not known).
2. OLD ROWS KEEP RANDOM IDS AND OTHER REVOKE PATHS STILL MAKE THEM. `DelegationToken.revoke()` (field_core/delegation.py:67) still draws a uuid4; only the API route overrides it (api.py:424). The only caller of `.revoke()` outside tests is that route (grep), so no other path today; tokens revoked before this change keep their random ids. LOW.
3. REPEAT EVENTS REMAIN. The ledger can hold several `delegation.revoke` events with the same id for one token (crash, second process). A consumer that counts events as revocations double counts; the README row says "at least once". LOW.
4. THE PER-TOKEN LOCK IS PER PROCESS. Two processes still both append; the conditional UPDATE keeps one row (same id now). Stated in the comment. LOW.

## Steelman
The fix is the structural one I recommended: make the id a function of the token so retries and losers write the same id, lock per token, and state the guarantee as at-least-once with a stable id. All three behave as stated under the probe.

## Mutants (24 tests in the file pass unmutated; file restored after each)
| Mutant | Result |
|---|---|
| random id again (uuid4) | 2 failed |
| one global lock (constant key) | 1 failed |
| no lock | 2 failed |
| id not derived from the token (constant) | 1 failed |
| lock entry never dropped; refcount not decremented | 1 failed each |
| already-revoked early return removed | 3 failed |
HIGH (observed). The earlier survivors list (C-701) had no crash-then-retry or two-process test; the file grew from 16 to 24 tests and those cases are pinned.

## Merge overlap
The card also asks about merge order with other PRs; not examined here.

## What I did NOT do
- No GX10 or estate run; real ledger service not used.
- Did not examine file overlap with other PRs.
- Did not measure timing over a network.

Full head: 1e3dea5a7fac517757e31290e125652930d6568c
