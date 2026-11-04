# Report: S-A4 (scout round 2), builder. UNVERIFIED (cloud, no GX10).
Claim check: no branch or comms note for SpendCap or token ceiling finiteness.
PR 502 (draft): https://github.com/SpinStateLabs/field-platform/pull/502, branch fix/spendcap-token-limit-finite-sa4, head 69e2f97a24c43455c85f17e38b0be7dc34d7d303 (one commit on main cd3b7690, noreply identity). Reviewer needed (Lane A).
Scope correction vs the scout: only +Infinity was accepted (R). NaN and -inf were already refused by the gt=0/ge=0 bound. SpendCap.limit and DelegationToken.max_spend_usd both took inf.
Fix: allow_inf_nan=False on both fields (two one-line changes). JSON schema unchanged (cannot express infinity). 20 tests, failing first (3 red), green; field-core 1564 passed 2 skipped; delegation-authority 257 and conformance-sentinel 263 passed (consumers); two mutants killed (2 red, 1 red).
Not run: other 13 suites; the YAML loader path with a literal `.inf` (tested through from_dict instead).
Open PRs by this builder: 488, 489, 490, 492, 493, 495, 497, 500, 502; none merged by me.
