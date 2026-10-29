# B-05 reviewer report (Lane 5): card-status sweep of comms/TASK-QUEUE.md

RESULT: 98 cards moved to DONE, 76 left (75 OPEN, 1 REVIEW) with a one-line reason each; no card deleted; one commit edits TASK-QUEUE.md and the B-05 line of BACKLOG.md; class and card ids only, no values.

COUNTS (cards starting `- C-n <state>`; 326 cards both times)
- Before: DONE 144, OPEN 163, REVIEW 11, NOTE 3, REASSIGNED 1, CLOSED 1, PART 1, PARTIAL 1, SUPERSEDED 1.
- After: DONE 242, OPEN 75, REVIEW 1, NOTE 3, REASSIGNED 1, CLOSED 1, PART 1, PARTIAL 1, SUPERSEDED 1.
- Moved to DONE: 47 builder or REVIEW cards with a merge, 51 reviewer cards with a report. The 174 edited lines are those 98 plus the 76 left open (each gets a bracketed `[sweep 2026-10-30 (B-05) ...]` note at the end of its line); nothing else in the file changed (174 lines in the diff).

METHOD (so it can be redone)
1. "Merged" is read from main, not from the PR state: most PRs here are CLOSED on GitHub (82 closed, 94 merged, 6 open at the time), because the coordinator lands them as new commits. A builder card is DONE when a commit on `origin/main` (91bf0c7 at the time) has the card id as its first reference in the subject, `(C-n,` or `(C-n)`; the note names the main sha(s) and the PR number(s) the card mentions. 47 cards.
2. A reviewer card is DONE when a report whose file name carries the card id exists in comms/inbox/coordinator/; the note names the file and its verdict (47 PASS, 2 FAIL, 2 audits). A reviewer card with no such file stays OPEN. 51 cards.
3. Left as is, with the reason on the line: 49 with no PR and no main commit naming them; 15 whose PR is closed and no main commit names the card; 4 whose PR (57) is still open; 6 cloud-reviewer or audit cards with no report; C-30 (REVIEW, no main commit); C-43 (the standing card).

WHAT I DID NOT VERIFY (objections first, in effect)
1. A main commit with the card id first in its subject is taken as the card's delivery. I read the 47 subjects against the card text, and a few cards list more than one deliverable (for example C-105 and C-147 have two main commits each, C-203 has two); I did not diff each commit against every clause of its card. If a card was only partly delivered it now reads DONE with the shas, so the clause is findable from the note. [MEDIUM]
2. A report existing is not the same as the card's done-when being met: the reports behind C-312 and C-313 are FAIL verdicts (the fix cards C-318 and C-319 are DONE with merges); C-202 and C-244 are audits (their notes say so). A reviewer card is done when the review was done, whatever the verdict. [HIGH]
3. Card numbers duplicated in the file: C-49 appears under two reasons in my tally (the file may carry two lines for it); I did not look. [LOW]
4. Cards that say "after PR n merges" and have a main commit are DONE; cards that say it and have no main commit stay open (for example C-84, C-88, C-94 are after PRs 59 and 61, which did merge; nothing on main names these three cards, so they are listed as left open and may in fact be stale). [MEDIUM]
5. The PR list came from `gh pr list --state all --limit 300` (182 PRs); a PR numbered above that window would be missed. [LOW]

LEFT OPEN, BY REASON (the coordinator can retire or restock)
- No PR and no main commit names the card (49): C-5, C-8, C-10, C-23, C-24, C-25, C-28, C-29, C-32, C-44, C-45, C-46, C-47, C-51, C-54, C-56, C-57, C-68, C-69, C-79, C-83, C-84, C-88, C-94, C-98, C-101, C-138, C-149, C-150, C-159, C-168, C-169, C-175, C-180, C-189, C-192, C-193, C-218, C-221, C-240, C-252, C-253, C-255, C-257, C-258, C-259, C-288, C-323, C-325. Several look superseded by later work (C-10 and C-94 STATE.md entries, C-79 and C-84 and C-88 on PRs 59 and 61 which merged, C-47 whose tool exists as comms/tools/gx10_verify.sh); I left them open because no commit names them.
- PR closed, no main commit names the card (15): C-26, C-106, C-128, C-216, C-260, C-267, C-287, C-298, C-299, C-301, C-304, C-305, C-315, C-316, C-322 (C-304's PR 181 is a draft, reviewed PASS in C-324).
- PR still open (4): C-12, C-15, C-18, C-38 (all on PR 57).
- No report in inbox (6): C-21, C-42, C-49, C-72, C-93, C-196.
- Other: C-30 (REVIEW), C-43 (standing).

CONCLUSION
98 of 174 candidate cards closed on evidence; the remaining 76 need a decision from the coordinator, listed above with the reason on each line of the queue. To undo: `git revert` of the single commit.
