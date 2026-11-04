# Report: scout P-6, evaluate_rogue unit tests. Builder. UNVERIFIED (cloud, no GX10).
PR 488 (draft, main): https://github.com/SpinStateLabs/field-platform/pull/488
Branch test/evaluate-rogue-unit-p6, head b667533797525f266f07947bfdd6b56447278e47 (one commit, on main cd3b7690, noreply identity author and committer). Reviewer needed (not this author).
Files: services/spend-governor/tests/test_evaluate_rogue_unit.py only. No source change.
Evidence on main: holds (no test names evaluate_rogue; burst is `>=`).
Ran: new file 13 passed; spend-governor suite 254 passed with test_throttle.py ignored (typer missing here, collection error, not triaged against main); hasattr(usage, 'evaluate_rogue') True from the in-tree src. Mutant `>=` to `>` (usage.py): 3 failed, restored. One mutant only.
Not run: GX10, full 16 suites, the throttle file.
Open: Field text "before rogue_burst" vs shipped `>=` is ambiguous; pinned as shipped, Don to rule if it should change.
Earlier same session: B-07 report 20261104-1500-builder-b07-pr57-vs-main.md; B-11/B-18/B-19/B-22 not claimable (see claim note 20261104-1530).
