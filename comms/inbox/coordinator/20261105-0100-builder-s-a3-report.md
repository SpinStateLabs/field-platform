# Report: S-A3 (scout round 2), builder. UNVERIFIED (cloud, no GX10). HIGH CARE: sealed-ledger append path.
Claim check: no branch or comms note for ledger non-finite payloads (a crosswalk NaN branch exists for a different card).
PR 500 (draft): https://github.com/SpinStateLabs/field-platform/pull/500, branch fix/ledger-reject-non-finite-payload-sa3, head 000fbeeb24dc691002537a8a0e260c884d7a39c4 (one commit on main cd3b7690, noreply identity). Reviewer needed (Lane A: field-core, sealed-ledger).
SEVERITY UPGRADE vs the scout (LOW reachability -> measured): on main, POST /events with payload NaN or Infinity returns 201 and GET /verify then says ok:false "hash mismatch ... (record was mutated)" (R: reproduced twice, both tokens). One request from a perimeter-secret holder makes the chain read as tampered. The seal hashes a NaN token; the served JSON has null.
Fix: field_core.ledger.reject_non_finite (iterative; message names neither value nor key); make_event calls it; AppendRequest.payload validator gives 422. _canonical_bytes and verification of existing events untouched.
Tests: 23 field-core + 4 sealed-ledger, failing first. field-core 1567 passed 2 skipped; sealed-ledger 806 passed 5 skipped 1 error (test_operator_observer_c6_serve, "ledger serve exited early", identical on clean main with my change stashed: baseline). Two mutants killed (9 red, 3 red).
Not audited: other writers (CLI, /rotate, /export payloads, LedgerClient callers); no real ledger searched for an existing NaN event.
Coordinator note: if any estate ledger already holds such an event it is already unverifiable; that is a separate read-only check I did not do and a deploy decision that is not mine.
Open PRs by this builder: 488, 489, 490, 492, 493, 495, 497, 500; none merged by me.
