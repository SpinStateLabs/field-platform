# Review PR 837 (G18: stage1_window, mechanical Stage 1 clean-window evaluation and gate G18 record) — ssl-ff-reviewer-7

**VERDICT: PASS WITH CONDITIONS** on head `3a435b7a6b18fff3f02d6838c3e07402c380dc11`.
Conditions: C1 (code, small, HIGH importance): `evaluate` must require all eight service labels in BOTH snapshots. I reproduced it: a pair of ONE-service snapshots 48 hours apart evaluates clean and, with `--records`, writes a `gate G18 ok:true` row with `services: 1`. G25 will rely on that row. C2: the clean window must be tied to now, or the row must carry the end time of the window: I evaluated a window from 2023-style timestamps (1.7e9 to 1.7e9+48h) and one whose `after` is in the year 2100: both clean; the row's `ts` is when it was evaluated, not when the window ended, so a stale pair of snapshots produces a fresh-looking G18 row. C3: CI and GX10 on the head. The PR body is stale on one point: it says "a decrease passes", the head (second commit) makes a decrease NOT clean (a restart); the code is the right one, the text should be corrected.

## Objections first
1. The check cannot see a restart that hides drops: the counters live in each process, so drops followed by a restart and equal counters at the next read look clean (my case 5). The docstring covers a decrease (a restart that goes down) but not this masked case; the design needs a process start time or uptime in `/health` to close it. State it as a limit in the docstring.
2. Trust model, stated by the PR: the snapshot files are local JSON that nothing signs and the records file is trusted by file permission; anyone who can edit the files can forge a clean window (a one-service pair is the unforged version of that).
3. Stage 2 does not read the G18 row yet (G25's card): this PR adds a record nothing consumes, so the gate is not enforced anywhere in this change.

## Checks (HIGH, run by me)
- Identity: 2 commits, author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com> on both; trailers Sonnet 5.5; .github/: 0 files. 3 files: tools/stage1_window.py (+161), tools/tests/test_stage1_window_g18.py (+241), one runbook line (+1/-1, the Stage 2 entry item now names the 24-hour window and the command). Based on main e125a878; main is f7408db5; new files, no overlap.
- Code read against the PR: reuses the controller's own `_increases`/`COUNTER_KEYS` (one definition of an increase); `snapshot` sends only unauthenticated `GET /<prefix>/health` and writes null for an unreadable counter or a service that does not answer as itself; `evaluate` fails on an empty or malformed snapshot, a non-forward window, a window shorter than `--min-hours` (default 24, not 0), an increase, a missing or non-integer counter on either side, and a counter that went DOWN; a PASS with `--records` appends one `gate G18` row (sha-bound when `--build-sha` is given, plus `window_hours` and `services`); a failure writes nothing.
- Tests on the exact head (Windows): test_stage1_window_g18.py 32 passed (the PR says 24: it has grown with the second commit); the PR also reports the controller and lint tests 304 passed (not re-run).
- Behaviour I ran: bad `--build-sha` with `--records`: prints "[PASS] the Stage 1 window is clean", then "refused: build_sha_invalid", exit 2, no record written (LOW ordering quirk: a PASS line precedes the refusal).

## Mutants (27 on stage1_window.py vs the 32 tests; counted from the table)
| group | mutants | killed | survived |
|---|---|---|---|
| window time W1-W7 (backwards, equal, min-hours off, boundary, default 0, default 1, bool timestamp) | 7 | 7 | 0 |
| counters I1-I3, M1-M5 (increase unjudged, decrease allowed / on equal, missing counter before / after, bool counter, empty before, after not object) | 8 | 5 | 3 (M1, M2, M3) |
| snapshot S1-S3 (name unchecked, status unchecked, authenticated call) | 3 | 2 | 1 (S2) |
| record R1-R7 (written on failure, no sha binding, ok false, wrong gate, wrong unit, build-sha without records, negative hours) | 7 | 7 | 0 |
| exits U1-U2 | 2 | 2 | 0 |
Totals: 27 mutants, 23 killed, 4 survived (7+8+3+7+2 = 27; 7+5+2+7+2 = 23; 0+3+1+0+0 = 4). Survivor reading: M1, M2, M3 are covered by the controller's `_increases`, which also flags a missing or non-integer counter, so the explicit missing-counter loop is redundant for the cases tested; S2 is covered by the service-name check. LOW. The real gaps are the ones above (eight labels, stale windows), which no mutant exercises.

## Optional LOWs (new PR)
Print the PASS line only after the record decision; a short statement of the restart-masking limit; a test that pins the eight labels once C1 is fixed.

## Not verified
CI/GX10; Linux; a real estate or a real snapshot of the eight services (my evidence is the unit tests plus my own probes on constructed snapshots).
