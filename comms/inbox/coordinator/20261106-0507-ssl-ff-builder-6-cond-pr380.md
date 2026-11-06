# builder-6: condition fix on PR 380
PR 380: old head 24d5482b -> new head 6127dd751ed7187f24a21ef33ce5858e0c1cdec6 (one tests-only commit; author+committer Don Hagell noreply). Applies reviewer-2 C1 (mutant W16).
Added test_the_outcome_row_carries_the_call_id_of_its_intent_row_and_each_call_has_its_own to services/field-mcp/tests/test_write_pins.py. Mutant: outcome row given a fresh uuid instead of the intent's call_id -> that test FAILS (killed).
C2 (rename body schema, mutant S6): already pinned at this head. With additionalProperties set True on the narrowed body (tools.py:85) test_tier2::test_schemas_offer_only_what_the_ruling_allows and test_a_rename_that_could_change_status_or_authority_is_refused[body7] FAIL (killed). No change needed.
Ran (PYTHONUTF8=1, Windows): test_write_pins.py 21 passed. `mcp` is not installed here, so the full field-mcp suite and test_stdio were not run.
NOT done: C3 rebase/GX10/CI, C4 supply-chain pins read by another reviewer. Re-review requested on 6127dd75. Note: later comms notes (20261111-1700 lane1 merge-368-into-380) suggest this stack is being merged elsewhere; coordinator to reconcile.
