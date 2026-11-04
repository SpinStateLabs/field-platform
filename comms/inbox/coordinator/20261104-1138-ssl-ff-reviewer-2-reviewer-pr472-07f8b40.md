# Reviewer report: PR 472 @07f8b40f (pin the Stage 1 to 3 runbook checklists, C-1187, Q-107 F8)

Reviewer: ssl-ff-reviewer-2. UNVERIFIED (cloud, no GX10). Python 3.13. One new test file, tools/tests/test_runbook_stage_checklists_c1187.py (+174); no runbook edit.

## Verdict: PASS WITH CONDITIONS (head 07f8b40fb961c68c864dfc2b8ecafb4d7a118205)
Conditions: C1 rebase on current main (PR base is c356e205, main is 97dcfec1); C2 GX10 16/16 on the exact rebased head (test PR, full run); C3 CI green. No blocking finding. I confirmed the 15 tests also pass against main's current runbook (it differs from the PR's by 3 lines): 15 passed.

## Objections first
1. The tests pin WORDS in a document no code reads; a harmless rewording turns them red and forces a same-commit test edit. Declared in the file docstring (HIGH, read). Accepted trade-off.
2. Whitespace-flattened substring pins pass if the sentence is moved into a different step or section and the markers still bracket it; stage membership is checked by `_stage()` slicing, so moving a sentence between stages is caught only where the pin reads a numbered step (HIGH, read).
3. Step numbers are positional (`_steps(...)[3]`): inserting a step shifts every pin and fails loudly, not silently (HIGH, read). Fails safe.
4. The PR text claims 16 hand mutants and 15 tests; I did not see the PR text's list, so I ran my own 35.

## Scope and identity
1 file; 1 commit; author AND committer = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). No secret or estate address in the file; only fake placeholders and runbook phrases (HIGH, read).

## Runs
Baseline (unmutated head): 15 passed. Mutants edit docs/runbooks/v1.2-deploy-rollback.md in a scratch worktree, one at a time; kill = the 15 tests fail; file restored after each (git status clean).

## Mutants
| Id | Behaviour | Mutation | Result |
|---|---|---|---|
| W1 | who runs | coordinator replaced by lane | KILLED |
| W2 | who runs | "Stages 1 to 4" cut to 1 to 3 | KILLED |
| W3 | who runs | Don's per-go-point confirmation dropped | KILLED |
| W4 | who runs | lane prohibitions cut to "never arms, never deploys" | KILLED |
| W5 | who runs | "a lane may arm" | KILLED |
| K1 | marks | stage 2 step 4 go-point mark removed | KILLED |
| K2 | marks | stage 1 step 6 mark removed | KILLED |
| K3 | marks | extra mark on stage 3 entry | KILLED |
| K4 | marks | "DON ONLY" label | KILLED |
| K5 | marks | Don's own step relabelled | KILLED |
| A1 | arm/rollback | "gate must print 8" dropped | KILLED |
| A2 | arm/rollback | stage 3 arm: delete override dropped | KILLED |
| A3 | arm/rollback | stage 3 rollback order flipped | KILLED |
| A4 | arm/rollback | reverse order flipped | KILLED |
| A5 | arm/rollback | stage 3 rollback checks enforce | KILLED |
| A6 | arm/rollback | stage 2 rollback checks enforce | KILLED |
| A7 | arm/rollback | stage 1 rollback "one flag line" | KILLED |
| A8 | arm/rollback | stage 1 rollback timing "after the arm" | KILLED |
| A9 | arm/rollback | stage 2 rollback recreates all, not kill-switch only | KILLED |
| C1 | canary | kill/revive scope widened to any agent | KILLED |
| C2 | canary | drill scope widened to the domain | KILLED |
| C3 | canary | domain kill allowed on an estate | KILLED |
| E1 | entry | open item only "noted" | KILLED |
| E2 | entry | key files `cat`ted | KILLED |
| E3 | entry | key modes loosened | KILLED |
| E4 | entry | verifier may use Don's key | KILLED |
| S1 | soak | invented 48 h floor | KILLED |
| S2 | soak | "take a number from this list" | KILLED |
| S3 | soak | "72 h" inside a stage | KILLED |
| S4 | soak | "at least 2 hours" added | KILLED |
| U1 | unpinned probe | "a step with no mark is read-only" dropped | SURVIVED |
| U2 | unpinned probe | "nothing here has been run; failing check stops" dropped | SURVIVED |
| U3 | unpinned probe | stage 2 "after ANY up" check weakened | SURVIVED |
| U4 | unpinned probe | stage 2 entry "override does not yet exist" flipped | SURVIVED |
| U5 | unpinned probe | stage 3 identity_present check weakened | SURVIVED |

Counted from the table: 35 rows (who runs 5, marks 5, arm/rollback 9, canary 3, entry 4, soak 4, unpinned probes 5). KILLED 30, SURVIVED 5. The 30 in-claim mutants (the behaviours the file says it pins) are all killed: 30 of 30. The 5 survivors are probes of text the file does not claim to pin; none equivalent. Per behaviour: who runs 5/5, marks 5/5, arm/rollback 9/9, canary 3/3, entry 4/4, soak 4/4, probes 0/5.

## Findings
- F1 LOW (HIGH confidence, run): U1 to U5 are unpinned. The "no mark means read-only" rule (U1) and the stage 2 step 7 rule that a `log-only` answer restarts Stage 2 (U3) are decision-bearing and cheap to pin. New PR, optional.
- F2 LOW: objection 2; no test proves a pinned sentence still sits in the stage it belongs to except through `_steps` indexes.

## Not verified
Rebase on 97dcfec1; CI; GX10; the PR text's own 16-mutant list.
