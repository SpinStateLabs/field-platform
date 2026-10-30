VERDICT: PASS WITH CONDITIONS on 112cf16d3328fc431c106d75f8e6d834a8ee2ef6

Reviewer Lane 15, cloud-reviewer, C-899, PR 385 (follow-up to PR 353/370). UNVERIFIED: no GX10 run; scratch-tree probes and mutants only.

## Objections first
1. Premise: the exit contract is 0 clean / 2 refused / 3 could-not-do-the-job, not 0/1/2. Exit 1 appears only when the script is copied alone and its sibling import fails (HIGH, probed). Symlinked script: fixed.
2. The tmpfs exemption in the model walk is unchanged: a volume with type tmpfs or device tmpfs skips the source check, so a bind-like entry with that marker reads clean (my C-787 objection 1; HIGH, probed). Not a C-735 condition, so not a regression, but still open.
3. Mutant survivor: the `must_be_text=True` flag on the service-volume bind branch has no test. Real code is correct (None, 123 and a list are each reported "is not a string"; probed), but removing the flag keeps all 41 new tests green (HIGH).
4. Junction roots (Windows) not probed: no Windows host (not verified).

## C-735 conditions
- F-C735-1 root behind a symlink under --realpath: CLOSED (original string resolved; allowed roots resolved too; declared spelling stays allowed).
- F-C735-2 non-string shapes read as clean: CLOSED (finding or exit 3 for non-mapping service, bad env_file shape).
- F-C735-3 lexical `..` before a link: CLOSED (exit 2 under --realpath, 0 without; documented as the posture limit).
- Objection 6 sibling import: CLOSED for a symlink, still fails for a lone copy (see objection 1).

## Relation to PR 353
Follow-up, not a replacement: PR 385 contains 353's 5d5cbf7 and 370's 1381b56 and must merge after them.

## Evidence
- tools tests: 41 new pass; 982 pass across c715, c512, c638, static pins (HIGH).
- Mutants on the new code: 10 tried, 9 killed, 1 survived (objection 3). Files restored; worktree removed.
- Commit identity guard on the PR commits: clean (7 commits).
- merge-tree against origin/main: clean, no conflicts.

## Conditions
1. Add a test for non-string bind source (objection 3). Non-blocking.
2. Close or explicitly accept the tmpfs exemption (objection 2). Non-blocking for this PR; blocking for any claim that the check is complete.
3. Merge order 353, 370, 385. Blocking only if merged out of order.

Not verified: GX10 behaviour, Windows junctions, interaction with PRs opened after this review.
