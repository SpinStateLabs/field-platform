# Review PR 408 @ 45a9bee473dc235b655b90f6405707071a3ac0ae (public-safety follow-up to C-758, scene4.mp4, skill guard) - reviewer ssl-ff-reviewer-3

**VERDICT: BLOCK on head 45a9bee4. UNVERIFIED (cloud, no GX10). No mutants written: the head cannot be applied to main, so a mutant result would not describe anything mergeable.**

## Blocking findings (HIGH, measured)
- F-R408-1: no merge base with current origin/main (97dcfec1; `git merge-base` fails); `git log origin/main..pr408` lists 433 commits. The PR's own work is 8 commits above acaf5f24 (the point where it forked from the old history; shared with PR 419 and PR 420): e7c53c46, 1ec3ff99, 9923f31c, d2dd0879, b2d52bb1, 686f9ee0, 364982fb, 45a9bee4; all 8 carry the numeric Don Hagell noreply identity for author AND committer (measured).
- F-R408-2: those 8 commits do NOT cherry-pick onto main 97dcfec1. `git cherry-pick acaf5f24..pr408` conflicts in `agents/ssl-timekeeping-agent/SKILL.md` and `manifests/ssl-timekeeping-agent.yaml` (commit e7c53c46). The same placeholders were already done on main by the scrub batch (STATUS MERGE 23: PRs 440, 448, 469 landed).
- F-R408-3: the head changes the owner contact in `.claude-plugin/marketplace.json` and `plugins/field-agent/.claude-plugin/plugin.json` to a placeholder mailbox. STATUS MERGE 23 says the coordinator restored the company's own contacts in exactly those two files by Don's ruling on Q-86 F1. This PR would undo a ruling; on current main the diff `origin/main..pr408` for both files shows the mailbox replaced. Do not land without Don.
- F-R408-4: `integration/video/out/scene4.mp4` (520735 bytes) is deleted by this PR; STATE.md says "no longer committed". Whether main still carries it was not checked here (I do not know).

## Not done
No mutants (see above), no test run. The new guard `tools/tests/test_skill_public_safety_c1088.py` (118 lines) was not exercised.

## Recommendation (coordinator's call)
Release PR 408. Anything still wanted from it (the structural guard test, and any placeholder lines not yet on main) is a new branch on current main, excluding the plugin/marketplace contact change unless Don re-rules; then a fresh review.

## Correction to the 1202 PR 420 report
Its commit-identity breakdown listed "50 correct author but committer GitHub". Those 50 have the author `dhagell@users.noreply` WITHOUT the numeric id, so they are not "correct". The totals (229 correct, 207 not) and the BLOCK stand.
