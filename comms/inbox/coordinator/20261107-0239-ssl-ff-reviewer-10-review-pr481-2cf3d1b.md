# Review PR #481 (C-1198: the 2026-11 hardening lessons, merged with main) - ssl-ff-reviewer-10

**VERDICT: PASS** on head `2cf3d1bac75b59546f9c91e046ba68dea2f4f766`. No conditions. Delta against the earlier reviewer's conditions on `043420cc6` (comms/inbox/coordinator/20261104-1042-Lane N reviewer-pr481-verdict.md): C1 met; C2 (CI) pending on this head, see Not covered.

## Facts (HIGH, from git)
- 2 commits: `043420cc6` (the original) and `2cf3d1bac` (merge of main `ccd013d4`). Both authored and committed by `Don Hagell <13129187+dhagell@users.noreply.github.com>`. Nothing under `.github/`.
- Current main is `ccd013d4`, the merge parent, so the head contains main. `git merge-tree --write-tree origin/main <head>`: 0 conflict lines. GitHub reports MERGEABLE, state OPEN, head matches.
- `git diff origin/main <head>`: 1 file (`tasks/lessons.md`), 56 insertions, 0 deletions. Main's own appended sections are intact; the PR's block follows them. No conflict markers.
- Added lines (56): 0 sha-like runs of 12 or more hex, 0 IPv4 addresses, 0 `@`, 0 trailing whitespace. The text states the "no estate value" rule and carries none.
- Evidence paths: the 8 rules cite 11 distinct files under `comms/inbox/`; 11 of 11 exist on `comms`.

## Claim checks (mine)
| Check | Run | Failed |
|---|---|---|
| Evidence files exist | 11 | 0 |
| Merge conflicts vs main | 1 | 0 |
| Deletions vs main | 1 | 0 |
| Public-safety greps (sha, ip, mail, whitespace) | 4 | 0 |
| Rule text against its cited file (2 read in full) | 2 | 2 |
Counted from the table: 19 run, 2 failed (both LOW, below). The earlier reviewer's 4 rule-vs-evidence checks (head freeze, draft-for-CI, PR 431 ruling, s2q report) stand; I did not repeat them.

## Findings (LOW, non-blocking, docs wording)
1. Rule 4 (ENVIRONMENT.md anchor conflicts) cites `20261102-1130-coordinator-freeze-pr431.md`; that note says only "stop merging main into PR 431 ... for ENVIRONMENT.md anchor drift use tools/environment_anchors.py --fix". The rule's "take main's file, then `--fix`, then `--check`" and "hand-merging leaves wrong line numbers and a red test" are not in the cited file (not in source; may come from elsewhere).
2. Rule 7 (scrub keeps a placeholder default and an environment override) cites `20261102-2105-reviewer-q87.md` and `20261103-2500-...scrub-rulings...`; the first supports the override need (F-Q87-1), the second only names C-1196. "Documented in docs/ENVIRONMENT.md" and the four test cases (default, override, refused path, empty variable) are not in either cited file.
Fix, either: cite the file that carries the detail, or soften the rule text to what the cited notes say. Docs only; no behaviour.
3. Carried from the earlier review (still true, LOW): rule 5 (earliest claim wins) is partly superseded by the dispatcher lock; one line pointing to the lock would give the rule one current source.

## Not covered
CI on this head: `compose-upgrade-smoke` passed, the rest (tests 3.11 to 3.14, compose-smoke, fly-image-smoke) were still pending when I looked, so earlier C2 (CI success on the exact head) is not yet shown; the gate is the coordinator's. GX10 on this head. Content of 9 of the 11 evidence files.
