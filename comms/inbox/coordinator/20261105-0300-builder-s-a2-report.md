# Report: S-A2 (scout round 2), builder. UNVERIFIED (cloud, no GX10).
Claim check: no branch or comms note for naive datetimes on DelegationToken.
PR 505 (draft): https://github.com/SpinStateLabs/field-platform/pull/505, branch fix/token-naive-datetime-sa2, head 86ea66f281b71e9aadfc546cabcafc93b37a75b9 (one commit on main cd3b7690, noreply identity). Reviewer needed (Lane A).
Scout's open question answered: the delegation-authority mint route already coerces a naive expires_at to UTC, so service-minted tokens are aware. The gap is the model (naive in -> TypeError in status()). I did not trace a real caller that supplies naive values today.
Fix: field_validator on issued_at/expires_at/revoked_at: naive -> UTC, aware keeps its offset. Coercion (matches the mint route), not refusal; Don may prefer refusal. Behaviour change for review: a naive value is now stored and serialised as aware UTC.
9 tests, failing first (5 red), green; field-core 1553 passed 2 skipped; delegation-authority 257, conformance-sentinel 263, lifecycle-manager 269 passed; one mutant 5 red.
Not run: other 12 suites.
Open PRs by this builder: 488, 489, 490, 492, 493, 495, 497, 500, 502, 505; none merged by me.
Scout round 2 status: done S-A1 (490), S-A2 (505), S-A3 (500), S-A4 (502), S-B1 (492), S-B2 (495), S-B3 (493), S-B8 (497). Not taken: S-A5, S-A6, S-B4..S-B7 (see 20261104-2000 file).
