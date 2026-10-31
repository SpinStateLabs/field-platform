VERDICT: PASS WITH CONDITIONS on 640e1bd15adef48d582a1974d8cf5fdfc7a31294

Reviewer Lane 15, cloud-reviewer, C-962, PR 355 (field-core tests only). The card names head fdc299c; the PR head is now 640e1bd (one new commit, tests only, +34 lines in test_operator_auth_format2.py). UNVERIFIED: no GX10, CI not read; scratch tree, made-up hashes through the retired-memory function.

## Objections first
1. The new commit answers C-847 F-C847-3 (the sightings counter cap); it does not touch F-C847-1 or F-C847-2, the real findings. The same-generation re-admit still reproduces on this head: after retirements at 42 (key A) and 43 (key B), a generation-43 file holding A is ACCEPTED, B at 43 is refused, a generation-42 file holding A is refused, generation 44 holding A is accepted (declared design) (HIGH, run). Production code is unchanged by the PR (tests only), so this is by construction (HIGH).
2. The mutant that would refuse it (`<` to `<=` at the retired-memory refusal test, operator_auth.py:1268) still survives the PR's tests: the whole format 2 and rotation test files pass with it (247 passed). Per C-847 that change is also too broad (it refuses legitimate same-generation re-reads), so the survivor is not a gap the PR can close by tests alone; it is the open design decision (C-847 F-C847-1/-2, carried) (HIGH on the survivor, MEDIUM on the design).
3. Nothing of this reaches a deployment: the PR changes tests only. The risk is false assurance, i.e. that "the cap boundary is pinned" is read as "the retired-key memory is sound" (HIGH).

## C-847 / C-889 conditions at this head
- F-C847-1 (same-generation re-admit neither refused, declared nor pinned): OPEN. PR 351's runbook declares a related same-generation case (a different file at the same number is not refused for hashes the first lacked); the retired-at-42, back-at-43 case is not declared there or in a test (HIGH).
- F-C847-2 (the broad fix is wrong; a narrower rule is the open design): OPEN, Don's call.
- F-C847-3 / my C-852 objection 2 (sightings cap at its boundary): CLOSED. New tests: cap 3 with three distinct sightings counts 3; cap 2 with four distinct sightings counts 2 and refuses all four; the same sighting three times counts once (HIGH, run).

## The boundary at cap-1, cap and cap+1
Retired table (operator_auth.py:1262-1265): removing the keep-newest slice step, or keeping oldest, or keeping one more, or evicting at cap+1 instead of cap: each killed by the PR's tests (4 of 4). Evicting at `>=` instead of `>`: SURVIVES, and is equivalent: at exactly cap entries the slice keeps all cap entries (HIGH, run and reasoned). Sightings set: cap boundary `<` to `<=`: killed; cap check removed: killed; counting the same sighting twice: killed (4 failed). Rotation-event generation 1 accepted and operator ids at and over the cap: pinned by the earlier commits (not re-run beyond the suite).

## Evidence
field-core 1128 passed, 2 skipped. 9 mutants on the retired memory and the sighting counter: 7 killed, 2 survived (one equivalent; one the open design). merge-tree with main and PRs 325, 351, 369, 374, 375, 383: no conflicts. Author and committer: the no-reply Don Hagell identity. Files restored; worktree removed.

## Conditions
1. Decide F-C847-1: a narrow production rule with its own reviewer, or declare it and pin the present behaviour (the carried C-889 C1). Non-blocking for this tests-only PR.
2. Card the production change separately (C-889 C3).

Not verified: CI, GX10.
