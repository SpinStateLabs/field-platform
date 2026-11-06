# Review PR #844 (E4: v1.2 Review block + lessons.md lines for Don's rulings) - ssl-ff-reviewer-10

**VERDICT: PASS WITH CONDITIONS** on head `b6d3e629ee16496c8c8935e8872d690a0be12e59`. Two conditions (C1, C2 below); both are one-line docs fixes, no code.

## Facts (HIGH, read from the head)
- 1 commit (b6d3e629); 2 files: tasks/todo.md (+9/-1, the v1.2 "### Review" block only), tasks/lessons.md (+28, 14 lines). Docs only; nothing under .github/.
- Author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- Scope source: architect decision comms/inbox/architect/20261106-1100-architect-E4-scope-and-deploy-scripts-ruling.md section 1 (four done-criteria). Criteria (1), (3) and (4) hold; (2) does not fully hold (C2).

## Review block (todo.md), checked against git: criterion 1 and 3 hold
- The "(filled at the end of each phase)" placeholder is gone; one line per phase A to G; Phase E correctly says it is not merged (only docs/capstone-evidence/v2-one-liners-source.md is on main: confirmed); the last line says chat-only corrections are not recorded here.
- All 30 cited commit ids resolve to exactly one commit each on origin/main (my script, 0 missing, 0 ambiguous), and each cited subject matches the phase text (for example 4b8b3523 is "D1 throttle + metering ... D5 federation outbound, X3 canary agent"; 9a2417c0 is the G21 provision `edit_refused`).
- No deploy status, address or build id appears in the added lines.

## lessons.md: each line checked against the four groomer files
Sources: comms/inbox/coordinator/20261031-0200-groomer-don-rulings-4.md, 20261104-2400-groomer-don-rulings.md, 20261105-0800-groomer-don-rulings-2.md, 20261105-2100-groomer-don-rulings-3.md. All 14 lines restate their ruling faithfully (C-467/D-21 WARN, C-561, C-563 option c, C-606, C-552, PR 348, D-19/D-20/D-18, D-6, C-478, soak item 1, PR 322 plus kill-switch guard, PR 57 hold lifted, D-9, D-12). D-31 (a confirmation) and D-16/D-25 (approvals) are rightly not written as lessons (D-16/D-25 are cited inside the C-563 line).

## Conditions
**C1 (MEDIUM, confirmed): the C-552 lesson is stale and now tells the next session to do the opposite of the standing ruling.**
The added line says "Defer alert senders until the rotator is reworked (C-552) ... Do not wire a sender early; keep the docs to what exists." Don's ruling of 2026-11-05 LIFTS C-552 (comms WORKLIST cards B-G23-alert-senders and B-G24-stage-controller: "Don ruling 2026-11-05 lifts C-552"), and the senders landed on main as fd0ac135 (G23), which this same PR lists in its Review block (Phase G). lessons.md is read at session start, so an agent would be told not to touch senders that main already has. Fix: reword the line to the current state (C-552's DEFER was lifted on 2026-11-05; the six senders are on main, G23; the three rotation senders have no caller until PR 57 is reworked, C-496), or drop it.
**C2 (MEDIUM, confirmed): criterion 2 ("none missing") fails, and the PR body's claim that no `*don-ruling*.md` file exists is wrong.**
The architect's scope names `comms/inbox/coordinator/*don-ruling*.md` as a source. The file `20261110-1740-builder-lane1-don-rulings-asked.md` (committed to comms 2026-10-31 despite its name) matches that glob and records eight rulings of Don's. By the PR's own rule (it wrote lessons for "keep" rulings PR 348 and PR 322), at least these qualify and have no line: item 7 (PR 381: the four proxy-environment clients WAIT for C-487, a deferral), item 1 (PR 395: contract writes stay fail-open when the ledger is down), item 3 (PR 325: keep the 2027-01-31 removal date), item 4 (C-504: leave the CLI print sites printing exception text to an operator terminal), item 6 (PR 372: keep the BLOCK-reason relay and add an SDK read size cap), item 5 (PR 383: operator log-only is not open). Fix: add the qualifying lines (or list each excluded item and the reason in the PR body) and correct the PR body's "no *don-ruling*.md file exists" statement. The PR body must list ids found versus written (criterion 2), and today that list is incomplete.

## Minor (LOW, optional)
1. The C-467/D-21 line's title says "A mismatch on an open service"; the source for C-467 says only "WARN (log line plus counter); no refusal", so "mismatch" is added context I cannot verify from the repo.
2. The soak line cites "PR 57 `_soak` 30 minutes, one 24-hour soak at the end" from round 4 (2026-10-31), while rounds 2 and 3 (2026-11-05) still list "soak item 3 (PR 57 `_soak` 24 h to 1 h)" as open for Don. I do not know which stands; the lesson follows round 4.
3. The PR body says "Not run: CI, GX10 light run"; the independent GX10 run on the exact head is the coordinator's gate, not part of this verdict.

## Not covered
Did not verify the meaning of every card id (C-478, C-459, D-6 and similar) beyond the ruling text in the four files; did not check docs outside these two files; did not rebase on current main.
