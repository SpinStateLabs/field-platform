VERDICT: PASS WITH CONDITIONS on ce328a1d955c3fa11819c64e6c1207a707a6e926
Card C-1027. The card names head ce328a1; the PR's current head is ce328a1 (GitHub API: 1 commit, 2 files, base acaf5f2, state open, mergeable_state unstable). Cloud reviewer, no GX10: UNVERIFIED. No other reviewer report on this card.

OBJECTIONS FIRST
1. CI is not green at this head: the REST check-runs for the sha showed 2 in_progress and 5 queued when I read them, none concluded. This is a docs-only change, but "not green" is the honest status; re-read by run id before merge.
2. The second edit (`docs/runbooks/v1.2-deploy-rollback.md:1000`) demands "at least one new event from each service" but the runbook gives no way to cause one. The live check before it is one canary `/check`, which produces a sentinel event only. A killswitch or delegation event needs an action the text does not name, so an operator cannot meet the sentence as written (F-C1027-1).
3. Failure conditions: (a) an operator reads "each service" literally and either stalls or skips the check; (b) "run C0 again if the soak was quiet" is read as a check of the gate when it only generates traffic; (c) other soak lines still say only "Soak ≥ 5 min" (tasks/todo.md:624, 630) and are not about signing, so they stay as they are, but a reader may assume the same quiet-soak rule applies.
Steelman: the edit is the smallest change that answers the finding, adds no figure, and the C0 reference is sound (below).

ASSUMPTIONS
A1 Scope is the three lines named in the card against C-447 F-C447-2 (20261102-0330-reviewer-c447-pr290-soak-times.md, line 33). A2 Docs only; nothing run.

REASONING
1. Diff `acaf5f2..ce328a1`: 2 files, 3 lines (runbook :949 and :1000, tasks/todo.md:440). No other change (git diff --stat). HIGH.
2. F-C447-2 asked that the A7 gate say "at least one canary event appended, then every event since arming is signed", and the same for the line near 1000. :949 now reads "Soak ≥ 5 min with at least one new event appended (run C0 again if the soak was quiet)", todo.md:440 the same without the C0 clause, :1000 "with at least one new event from each service (a quiet soak proves nothing)". All three closed in intent. HIGH.
3. "Run C0 again" is sound: C0 step 3 (tasks/todo.md:405-422) runs `/check canary.probe` and `/check canary.forbidden`, each with +1 event, so re-running C0 appends events. HIGH.
4. :1000 does not follow from the same procedure: C0 produces sentinel events only; the per_caller line the check reads covers services that append during the soak. The loop above it checks key loading for sentinel, killswitch and delegation by log line, not by an event. MEDIUM.
5. No new figure: the only number in the diff is the existing "5 min". HIGH. No estate address, flag value, build SHA or deploy status in the three lines. HIGH.
6. F-C447-1 is PR 392 (C-911) and F-C447-4 is Don's rule with the coordinator writing the STATE line, per the card; neither is in this PR. Not checked here.
7. Authorship: author and committer Don Hagell no-reply (git log). `git merge-tree` of PR 393 with origin/main: exit shown in my run (clean if 0).

FINDINGS
F-C1027-1 (LOW, no block): :1000 requires an event from each service with no way to cause one. Say how (for example "run C0, and one action per service that appends") or reword to "at least one new event" plus naming the sentinel canary.
F-C1027-2 (INFO): CI queued/in progress at read time.

CONDITIONS
C1 (non-blocking) F-C1027-1. C2 (before merge) CI green by run id.

NOT VERIFIED: CI result, F-C447-1 and -4 elsewhere, any live run of the steps.

CONCLUSION
The three lines close F-C447-2 in intent, change nothing else, and add no figure; the per-service clause at :1000 cannot be met by the stated procedure. PASS WITH CONDITIONS, UNVERIFIED.
