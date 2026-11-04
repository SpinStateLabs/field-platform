# Reviewer report: PR 599 @ 9e20e9a1f0edb3c36ff900c58919b18ca0e0ce48 (force-gateway: hygiene heuristics count curly apostrophes, S2-14)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). One commit on origin/main 97dcfec1 (main is now b963407a; `git merge-tree --write-tree origin/main pr599` is clean). 2 files (+49/-2): force_gateway/telemetry.py (+6/-2) and tests/test_telemetry_heuristics.py (+43). Author and committer Don Hagell 13129187+dhagell@users.noreply.github.com, trailer Sonnet 5.5 (HIGH).

## Objections first
1. The claim is "the heuristics count curly apostrophes". The patterns that contain an apostrophe are: `i'd be happy to`, `i don't know` and `that (is|'s) incorrect`. The PR's tests cover the first two only. I probed the third on this head: `analyze("That’s incorrect.")` and `analyze("That's incorrect.")` both give `corrections: 0` (run by me, HIGH). The regex `that (is|'s) incorrect` demands a SPACE between "that" and `'s`, so it can never match "that's incorrect" with any apostrophe: a pre-existing dead alternative that this PR neither introduces nor fixes, and that its curly-apostrophe claim does not reach.
2. `test_the_text_is_normalised_on_a_copy_only` cannot fail: Python strings are immutable, `text.translate` returns a new string, so `assert text == ...` holds for any implementation. It pins nothing.
3. The normalisation runs before every pattern, including patterns without apostrophes; a regression there is harmless, but it also means one mapping decides all matches.

## Verified (run by me)
- Baseline on the exact head: tests/test_telemetry_heuristics.py 19 passed (relative PYTHONPATH).
- The comment fix is accurate: the `[E]` comment now says bold or bracketed only, and `_CONFIDENCE` is bold or bracketed only; a bare "HIGH — ..." is not counted (pinned by the tests: "HIGH — directly verified" -> 0, "HIGH: x" -> 0, "**high**" -> 0).

## Mutants (mutations of telemetry.py; scratch worktree on the head; baseline 19 passed; kill = at least one failure)
| # | Mutant | Result | Killed |
|---|---|---|---|
| N1 | U+2018 not mapped | 1 failed | yes |
| N2 | U+2019 not mapped | 2 failed | yes |
| N3 | normalisation not applied | 3 failed | yes |
| N4 | curly mapped to a double quote | 3 failed | yes |
| N5 | curly mapped to nothing | 3 failed | yes |
| N6 | normalisation moved after the confidence count | 19 passed | NO (equivalent: that pattern has no apostrophe) |
| F1 | flattery "great question" removed | 1 failed | yes |
| F2 | flattery "i'd be happy to" removed | 3 failed | yes |
| F3 | flattery "certainly!" removed | 1 failed | yes |
| F4 | flattery pattern case-sensitive | 9 failed | yes |
| E1 | bare HIGH counted as a confidence tag | 2 failed | yes |
| E2 | bracketed tags removed | 2 failed | yes |
| E3 | bold tags removed | 2 failed | yes |
| S1 | "i don't know" removed from source honesty | 2 failed | yes |
| C1 | correction alternative "that's incorrect" removed | 19 passed | NO (see objection 1: the alternative is dead, nothing to pin) |
Totals counted from the table: 15 mutants, 13 killed, 2 survived (N6, C1). Survivors against the whole force-gateway suite: not run; no other file in this PR's scope exercises the correction pattern (I grepped nothing outside the test file, so "survives" means this test file only).

## Findings
- F-S214-1 MEDIUM-LOW (pre-existing, found here): the correction alternative `that (is|'s) incorrect` in telemetry.py `_CORRECTION` never matches "that's incorrect"; fix to `that(?: is|'s) incorrect` and add a case with both apostrophes. Not introduced by this PR; belongs in a follow-up or in this PR as a condition fix, the coordinator's call.
- F-S214-2 LOW: the "normalised on a copy only" test is vacuous (objection 2); delete it or replace it with a test of an observable property.
- F-S214-3 LOW: N6 is equivalent, nothing to do.

## Verdict: PASS on 9e20e9a1f0edb3c36ff900c58919b18ca0e0ce48
The change does what it says for the patterns it tests (13 of 13 relevant mutants killed); the dead correction pattern and the vacuous test are LOW follow-ups. Head frozen; follow-ups go in a NEW PR. CI green and the force-gateway suite on this exact head per the coordinator procedure (light run is not allowed: it changes code). Not run by me: CI, GX10, the whole force-gateway suite.
