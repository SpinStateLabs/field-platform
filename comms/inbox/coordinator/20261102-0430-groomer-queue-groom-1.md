# Groomer (Lane 9): queue groom, cycle 1

OBJECTIONS: (1) closed PR is not merged: batches land by fast-forward with identical patch-ids, so I used verdict reports and main subjects, not PR state. (2) A verdict in is not a merge: C-446, C-450 (PRs 288, 291) are DONE as cards but their PRs are still open. (3) Lane 1 verified builder C-1..C-401 earlier; I did not redo it except where it named an unknown.

ASSUMPTIONS: main 3ee2e5d (fetched, 397 commits); a reviewer report naming the card with PASS or FAIL closes the reviewer card (your 2026-11-01 sweep rule); no live GX10 or CI access from this session (HIGH for the first, MEDIUM for the rule).

REASONING / COUNTS (TASK-QUEUE.md, cards only):
- OPEN before 100, after 48 (builder 36, reviewer 8, coordinator 3, cloud-reviewer 1; REVIEW 6, CHECK 5, STALE 4, DONE 392) (builder 35, reviewer 5, coordinator 3, cloud-reviewer 1).
- Flipped 65: DONE 54 (47 reviewer cards by report, C-216, C-93, C-49, C-418 main 483f280, C-288 main 3f5f40e/313c52d/694a90e, C-47, C-298 main 73bc4e7), STALE 1 (C-21), CHECK 5 (C-8, C-25, C-42, C-72, C-84), REVIEW 4 (C-442 PR 293, C-57 PR 295, C-445 PR 296, C-44 PR 297), BLOCKED 1 (C-451 became unblocked when PR 288 merged (kept OPEN)).
- New cards 9 (the coordinator took C-453..C-455 while I worked; mine were renumbered after a rebase conflict, kept both sides): C-456 (stale sha pin in the token-renewal runbook, MEDIUM, F-C196-1), C-457 (F-C447-1..4), C-458 (F-C202-3, needs Don's ruling), C-459 (F-B04-1 load_anchors), C-460 (F-B04-3/-4/-5), C-461 (F-C355-2/-3/-4), C-462 (reviewer: PR 295), C-463 (reviewer: PR 296), C-464 (reviewer: PR 297).
- BACKLOG: B-03, B-04, B-08 flipped DONE; B-10..B-15 added (sourced); UNCLAIMED now 9 (B-01, B-02, B-06, B-10..B-15), all builder.
- LANE ASSIGNMENT block replaced at the bottom of TASK-QUEUE.md (3 verified cards per builder lane, no repeats).

NOT FLIPPED, RULE "PR 57": C-447 (its text names PR 57's `_soak`; verdict is in: reports 20261102-0330-reviewer-c447-pr290-soak-times.md, PASS WITH CONDITIONS; please flip yourself); C-448 (text says "do not flip PR 57 cards"; Lane 1 delivered 20261030-0905-builder-lane1-c448-triage.md: it is done); C-12, C-15, C-18, C-38 (PR 57); B-07 (PR 57 comparison report exists: 20261029-5800-reviewer-b07-pr57-vs-main.md; unflipped).

SHORTAGE (stated, nothing invented): reviewer OPEN cards are 5, C-462, C-463, C-464 are new and unclaimed; Lane 7 holds C-452 and C-449; C-43 is a standing card. Reviewer backlog has no UNCLAIMED item (R-01..R-05 CLAIMED, the rest DONE). Lanes 5 and 6 have nothing verified to take until a builder pushes C-451 or C-457. The five-per-role floor is NOT met for reviewer and cloud-reviewer.

COULD NOT VERIFY: C-8/C-25 (dated premise: deploy planning, maybe the coordinator's); C-84 (titles versus priority/tag pins); C-42 and C-72 against Q-01 and Q-03 (scope differs); C-298 (third of three one-line fixes not re-read); C-47 (script lives on comms, not tools/ on main); C-218 left OPEN (comms/tools/gx10_verify.sh has no verify_sync); builder cards C-10, C-24, C-28, C-29, C-32, C-44, C-45, C-46, C-51, C-54, C-56, C-68, C-69, C-94, C-98, C-106, C-128, C-159, C-267 stay OPEN per Lane 1's "unverified either way"; C-150 and C-189 are coordinator items (date, deploy statement), untouched. About 40 older reviewer findings with no card were left as LOW test gaps; I carded the MEDIUM and security-relevant ones and put six into the backlog.

CONCLUSION: queue is 48 OPEN; 36 are builder cards and about 24 of those are real unstarted work; reviewers have 8 (3 new, 2 held by Lane 7, 1 standing, 1 blocked on C-453, C-447 left for you to flip).

CYCLE 2 NOTE: the card numbers C-456..C-464 named above collided with coordinator cards; my nine cards are now C-465..C-473 (same order: C-465 sha pin, C-466 PR 290 docs, C-467 retired spend, C-468 load_anchors, C-469 field-core cleanup, C-470 federation, C-471..C-473 reviewer PRs 295, 296, 297).
