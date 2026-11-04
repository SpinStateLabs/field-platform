# Lane O reviewer: PR 488 (scout P-6, spend-governor evaluate_rogue unit tests) @b667533797525f266f07947bfdd6b56447278e47. UNVERIFIED (cloud, no GX10, CI not seen)


VERDICT: PASS WITH CONDITIONS, naming head b6675337. Tests only (1 file, +75), no source change; contains main cd3b7690; one commit, Don Hagell noreply author and committer (HIGH). Lane B (spend). I did not write the head.

Objections: (1) the test file pins `>=` at the burst boundary although the Field text says "before rogue_burst" (the docstring admits the ambiguity): the test freezes shipped behaviour that may be wrong; that is a Don ruling, not a test defect. (2) pure-function tests do not prove the callers pass window_tokens_after INCLUDING the event (usage.py docstring); a caller off-by-one would not be caught here. (3) limit=0 and case sensitivity of the allow-list are unpinned (survivors below).

Run here: PR test file 13 passed; whole spend-governor suite 304 passed (relative PYTHONPATH of every service src and packages src).

Mutants on usage.py evaluate_rogue (scratch worktree on the exact head; each against the PR file, survivors against the whole service suite; one mutant did not apply and is excluded from the counts):
| Behaviour | Mutants run | Killed | Survived |
|---|---|---|---|
| B1 burst boundary is >= (gt, +1, lt, eq, -1) | 5 | 5 | 0 |
| B2 no limit never bursts | 4 | 2 | 2 |
| B3 policy None gives nothing, unpriced still fires | 4 | 4 | 0 |
| B4 allow-list (empty never fires, not-in, names the model) | 6 | 4 | 2 |
| B5 stable order unpriced, model, burst | 4 | 4 | 0 |
| B6 burst detail names tokens, window, limit; kind | 4 | 4 | 0 |
| Total (counted from the rows) | 27 | 23 | 4 |
Plus 1 NOAPPLY (detail-no-model string did not match; not counted).

Survivors (4, all LOW pin gaps, none equivalent):
- F-O488-1 LOW (2 mutants): token_rate_limit = 0. `is not None` fires at any token count; mutants "falsy check" and "or 0" treat 0 as no limit or equal. Whether 0 means "block everything" or "unlimited" is undecided in the tests. usage.py: `policy.token_rate_limit is not None`.
- F-O488-2 LOW: the rogue-model detail test asserts the model name only; dropping the allow-list text survives.
- F-O488-3 LOW: allow-list match is case-sensitive; a `.lower()` mutant survives, no test pins it.

CONDITIONS (blocking): C1 CI green on the exact head; since tests only, a light GX10 run (core+touched suite) may be used and must say "tests only". Not run by me.
Optional, NEW PR only after the head is frozen: F-O488-1/2/3 pins; a caller-level test for objection 2.

Tokens/cost line: not available to me. I do not know.
