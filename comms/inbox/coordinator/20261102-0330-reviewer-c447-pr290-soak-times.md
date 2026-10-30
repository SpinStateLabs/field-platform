VERDICT: PASS WITH CONDITIONS on 33b2c0234db44cc7b1a281b6824b421676adf76f

Card C-447, PR 290 (docs: soak times, Don's instruction 2026-11-01), Lane 7. Head confirmed by PR read: 33b2c02, one commit on base 7e8f16e. Main has since moved to 3ee2e5d; the commit cherry-picks onto 3ee2e5d with no conflict. A PASS applies to this SHA only.

Condition (one, docs, not a blocker for merge if Don accepts it): the PR leaves `C0 every 15 minutes` inside 5-minute soaks (F-C447-1 below). Either fix the two lines or record Don's acceptance.

OBJECTIONS (before evaluation)
1. A shorter soak is weaker evidence: an arming step that fails slowly (a restart loop with back-off, a scheduled job, a log-rotation or a signing fault on a low-traffic ledger) is invisible in 5 minutes. The step order (GB10 first, then Fly) stays, but the time between is the safety margin. This is Don's decision, not a defect of the PR; I flag it, I do not rule on it.
2. A mechanical edit can leave a sentence that no longer makes sense: "5 min soak with C0 every 15 minutes".
3. A gate that counts "every new event" over 5 minutes can pass with zero new events (vacuous).
4. The 24 h-class soaks cannot be shortened by text alone if the evidence check is an interval the services set (86400 s).
5. A pin in a test on the old wording would go red or, worse, be edited to fit.

ASSUMPTIONS
A1. The instruction is Don's: "all soak times 5 minutes, except 24 h soaks 1 hour" (card C-447, PR body). I did not see the original message (not in source).
A2. "Soak time" means a stated waiting duration in an operator runbook or plan, not history in STATE.md or comms reports.

REASONING
1. `git diff -U0` on the PR: 10 lines removed, 10 added, in 3 files. The card and the PR body say 9; the diff and the PR API (additions 10, deletions 10) say 10. I believe the diff. The count is wrong in the text, not the change (HIGH).
   Lines: docs/runbooks/v1.2-deploy-rollback.md :925, :949, :1000; tasks/next-session-phase-f.md :60; tasks/todo.md :282, :426, :440, :477, :624, :630.
2. Each of the 10 changed lines differs from its old text only in the duration (`≥ 1 h` to `≥ 5 min`; `30-minute` to `5-minute`). I compared old and new line by line; nothing else moved (HIGH).
3. `git grep` on the head over docs/ and tasks/ for soak with 1 h, one hour, an hour, 30 min, 60 min: no remaining match. The remaining durations are the ≥ 25 h scheduler soak (tasks/todo.md :512, :601, :674) and the 86400 s check (:646) (HIGH).
4. Outside docs/ and tasks/: STATE.md records soaks that happened and Don's dated decisions (for example :1101 "A9 go after a clean ≥ 1 h A7 soak"); they are history and the PR is right not to edit them (MEDIUM). packages/field-core/tests/test_alerts_ntfy.py:385,390 uses "24 h soak" as sample text for an alert body; unrelated (HIGH).
5. Tests: whole `python -m pytest -q tools/tests` on main 3ee2e5d plus the cherry-picked PR: 2806 passed, 7 skipped, 709 s. I did not list the 7 skips on this run (no -rs); on a second tree I run with -rs and will report them if they matter. No test pins the old texts: grep over tools/tests and services/*/tests for the old soak durations found none (HIGH).
6. The four items the PR lists as NOT changed:
   a. Scheduler soak (≥ 25 h; evidence `swept_at` > StartedAt + 86400 s, defaults FIELD_LIFECYCLE_EVERY and FIELD_CROSSWALK_EVERY = 86400): I agree it must stay. A 1 h soak cannot show a sweep that runs every 24 h; shortening the text would make the evidence unobtainable. It needs Don's decision on the interval, a behaviour change (HIGH on the PR body's own citations; I did not read the compose defaults myself: MEDIUM).
   b. `C0 every 15 minutes` (todo.md :477, :624): I disagree with leaving it. The PR changed those very lines to "5 min", so the lines now read "≥ 5 min soak with C0 every 15 minutes": a 15-minute cadence inside a 5-minute window means C0 runs once at the start, or never. See F-C447-1 (HIGH, line read).
   c. Key-rotation soak in held PR 57 (rotation.py _soak): agree, not on main, held for Don (HIGH, per the card).
   d. Scripts outside the repo (gb10-a7-soak.sh and friends): not in source; I did not read them and cannot judge. They could still wait the old duration, so the runbook and the script would disagree (LOW, unverified).

FINDINGS
- F-C447-1 MEDIUM-LOW, docs, tasks/todo.md:477 and :624: "≥ 5 min soak with C0 every 15 minutes" cannot be executed as written. Fix: "C0 at the start and at the end of the soak" (or "every 5 minutes"). Probe: read the two lines; the cadence exceeds the window by 3 times.
- F-C447-2 LOW, docs, docs/runbooks/v1.2-deploy-rollback.md:949 and tasks/todo.md:440 (A7 gate "every event appended since arming carries signature", "every new event signed"): over 5 minutes this can be true with zero new events. Suggest the gate says "at least one canary event appended, then every event since arming is signed". Same for :1000. (MEDIUM: depends on ledger traffic, which I do not know.)
- F-C447-3 LOW, text count: PR body and card say 9 lines; the diff has 10. No action beyond correcting the PR text.
- F-C447-4 LOW, decision for Don: STATE.md :1101 records Don's 2026-09-14 standing go "A9 after a clean ≥ 1 h A7 soak"; the new 5-minute rule supersedes it for the runbook. A one-line note in the next STATE.md entry that the 2026-11-01 instruction replaces the 1 h would stop a later reader quoting the old gate. Not a defect of the PR.

Mutants: not applicable (docs only; no code). The nearest equivalent I ran: a `git grep` for every old spelling (1 h, 1-hour, one hour, an hour, 30 min, 60 min, 30-minute) on the head: 0 hits in docs/ and tasks/.

CONCLUSION: PASS WITH CONDITIONS on 33b2c0234db44cc7b1a281b6824b421676adf76f. The change is exactly the soak durations (10 lines, not 9), nothing else moved, no old soak left in docs/ or tasks/, no test pins the old text, and the four "not changed" items are mostly right to hold, except the C0 cadence, which the PR itself made inconsistent (F-C447-1). CI on this head: not read by me (the coordinator needs 7 of 7 and GX10 16/0 on the exact head).

What I did NOT do
- Not run on the GX10 (cloud session); local Python 3.13 only.
- Did not read CI for this head, the scripts outside the repo, or the compose defaults for the 86400 s intervals.
- Did not list the 7 skipped tests of the tools run.
- Did not see Don's original instruction; I relied on the card and PR body.
