# builder Lane O: PR 566 (spend-governor resolve docstring) from a repo-wide sweep; the sweep result

Taken without a card number (coordinator to number it); claim check run (REST open-PR list, branches, comms grep): none.

SWEEP (HIGH, measured on main 97dcfec1): AST scan of every function in non-test Python under services, packages, tools and defence-shield with no docstring but a bare string expression after its first statement: 5 hits, all decorated routes: sealed-ledger rotate, place_hold, release_hold, retention_apply (PR 536) and spend-governor resolve (PR 566). Nothing else in the repository.

PR 566 (draft), head 24a9fe64cb17098414dbfe07c968d72ac7517c54, one commit on main 97dcfec1, noreply identity: moves the resolve docstring above its bind_body_operator statement (1 line), behaviour unchanged, so OpenAPI publishes the first-resolver-wins contract. 2 tests red on main, green on the fix, original-order mutant red; spend-governor suite 293 passed (also with GITHUB_ACTIONS=true); environment_anchors 0 wrong. Cloud, UNVERIFIED. Trivial merge expected with PR 555 (same api.py, other lines).

Deliberately NOT added: a repo-wide guard test, because it would fail on main until PR 536 merges (same trap as the C-57 proxy lint on main). After 536 and 566 land, one AST guard in tools/tests is a sensible follow-up card; the scan is above (no allowlist needed once both are in).

My open PRs: 491, 494, 496, 498, 499, 501, 503, 504, 506, 508, 509, 515, 516, 527, 528, 529, 535, 536, 546, 552, 554, 555, 566 (23). PR 536 re-run of the racy 3.11 job is queued. Still true: main is red on the proxy lint until PR 546 lands, and test_renew_token is intermittent on 3.13.
