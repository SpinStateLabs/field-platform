VERDICT: PASS WITH CONDITIONS on ba35c14a4605e5e128f3a2ae03e5399080cbe6da

Reviewer Lane 15, cloud-reviewer, C-908, PR 349 (delegation-authority idempotent revoke), builder Lane 2's head after C-821 (three commits since 1e3dea5: only 2ab288f's wording and 1e3dea5..ba35c14 delta of 4 files, +75/-15). UNVERIFIED: no GX10, CI not read; in-process probes with the real ledger and registry apps.

## Objections first
1. The guarantee is still at-least-once, not "one event per revoke". A crash between the ledger append and the store write leaves the ledger with a revoke event while the token still introspects active, until someone retries. The README and the code comment now say "revoke REQUESTED" (api.py:413-419), which is honest, but no sweep finishes an orphaned revoke (named out of scope by the builder) (HIGH, run).
2. Probe shows the window is real: after an injected crash in the store write, 500 returned, the ledger held 1 event, `/introspect` answered active; the retry returned 200, the token became inactive, and the ledger then held 2 events with 1 distinct revocation id (HIGH, run).
3. C-797 condition 4 (unknown versus revoked on introspection) is unchanged and is not in the C-821 delivery note: `/introspect` answers an unknown id with a fixed reason, null agent and empty scope, and a revoked id with its agent, scope, expiry, issuance time and reason "token is revoked" (observed). The form route `/oauth/introspect` answers `{"active":false}` for both, byte for byte (observed). Two disclosure policies for one question; open, Don's decision (HIGH).
4. The 502 text for a transport failure still includes the underlying exception text (api.py:441-442: "ledger unreachable — refusing to revoke: {exc}", where the client builds str(exc) of the transport error). That can carry a ledger address to the caller of an operator-guarded route. Not in this delta; LOW, not verified what a real transport error prints (MEDIUM).
5. The revocation id is a public function of the token id (C-797 objection 1, stable_revocation_id): unchanged and out of this delta (HIGH).

## C-692 (Lane 4, on 1e3dea5) conditions at this head
- F-C692-1 (at-least-once, visible window and duplicate): STATED, not fixed (README row and comment); a pinned wording test exists per the builder. Closed as documentation, open as behaviour (objections 1-2).
- F-C692-2 (unknown-id 404 and race-loser response unpinned; 2 of 19 mutants survived): CLOSED. The unknown id is pinned as a response (404 observed on the route; a path-style id and 300-character id per the builder); the loser returns the stored row. The reviewer's bare-raise mutant sits in an unreachable branch (the first read already answers 404 and the store has no delete); I did not re-derive that equivalence (not verified).
- F-C692-3 (ledger refusal reported as "unreachable"): CLOSED. Status 403 and 500 give "ledger refused (HTTP n)", no status gives "ledger unreachable"; all three return 502 with the token unrevoked (HIGH, run). Only the status is formatted, never the body (mutant that appends the exception text: killed).
- F-C692-4 (unused flag): CLOSED; save_revoked returns the stored token.

## Scenarios the card names (probed on this head)
- Retry after a ledger failure: 502 (unreachable), 502 (403), 502 (500), token still active; then 200 and 200 with the same revocation id; 1 event (HIGH, run).
- Crash between ledger and store: objection 2.
- Concurrent revokes: 16 simultaneous revokes of one token through one app: all 200, 1 event, 1 revocation id. Two apps over one sqlite file are pinned by the existing test at tests/test_revoke_c625.py:240-260 (not re-run separately) (HIGH for one app).
- Unknown versus revoked: objection 3. Unknown revoke target: 404.

## Evidence
- Suite: 243 passed in services/delegation-authority (matches the builder's 243).
- Mutants on the delta: 7 applied, 7 killed (status branch removed or inverted, body text appended, the "not yet revoked" condition removed, returning the candidate instead of the stored token, wrong status code, a global lock key). One no-op discarded. Files restored; worktree removed.
- merge-tree: clean against origin/main and against PRs 352, 358, 361, 369, 374, 375, 381, 383.
- Author and committer: the no-reply Don Hagell identity on all three commits.

## Conditions
1. Decide introspection disclosure (objection 3): non-blocking.
2. Decide a sweep or accept "requested" semantics; any ledger consumer must read the event as a request: non-blocking, wording is in place.
3. Check the transport-error text for an address (objection 4): non-blocking.

Not verified: CI, GX10, a real network ledger, a second process.
