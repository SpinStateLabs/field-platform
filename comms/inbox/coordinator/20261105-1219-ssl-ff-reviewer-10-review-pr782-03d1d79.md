# Review PR #782 (conformance-sentinel: pin routing.needs_semantic_judgment, S8-24, tests only) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `03d1d79a61cf4b36d5ad82da3c16020b84d1b3a9` (draft, base main). Optional LOWs go in a NEW PR.

## Facts (HIGH, read from the head)
- 1 commit, 1 file added: services/conformance-sentinel/tests/test_routing_predicate.py (+125). routing.py and the engine untouched. Nothing under .github/. Author AND committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- 31 tests pass on the head (0.06 s). Expected values re-derived by me from routing.py: `_WORD = [a-z0-9]+` after `.lower()`; ten stopwords; exact membership short-circuits; any shared content token routes. The Cyrillic (no tokens) and accent-split (`créer` to `cr`, `er`) claims follow from that regex (HIGH).
- The ASCII-only tokenizer limit is pinned as current behaviour: a future Unicode fix will turn three tests red on purpose (they say so); it is the author's open decision for Don, not a defect of this PR.

## Mutants (routing.py, one at a time, restored after each)
| # | Mutant | Result |
|---|--------|--------|
| M1 | exact-membership early return removed | RED |
| M2 | stopword filter removed | RED |
| M3 | `.lower()` removed | RED |
| M4 | tokenizer widened to Unicode words | RED |
| M5 | `any` to `all` over scope entries | RED |
| M6 | `if not tokens` guard removed | SURVIVED (equivalent: empty tokens intersect nothing; author names it) |
| M7 | exact check strips the action | RED |
| M8 | exact check case-folded | RED |
| M9 | digits dropped from tokens | RED |
| M10 | underscore added to tokens | RED |
| M11 | "the" removed from stopwords | RED |
| M12 | scope not copied with list() (generator case) | RED |
| M13 | requires two shared tokens | RED |
Totals counted from the table: 13 mutants, 12 RED, 1 SURVIVED (equivalent).

## LOWs (optional, new PR)
1. `test_stopword_only_overlap_does_not_route` mixes three behaviours in one test (first asserts a True, mislabelled by its name); harmless, rename only.
2. Decision (author's, Don's): whether non-English actions should route to the judge; moves judge cost and scorecard coverage numbers.
