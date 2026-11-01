# Builder Lane 11: B-17 PROPOSAL (rule for "far") for the claude-approver cursor. No code written; waiting for a go

Card: BACKLOG B-17 (reviewer C-463 F-C463-1): a VALID but absurd `processed_at` (`9999-12-31T23:59:59Z`) becomes the cursor and stays, so the next read sends `created_at_gte=9999-...` and no real event of that session is returned until the process restarts. The card says to propose the rule for "far" first. Sources read: services/claude-approver/src/claude_approver/core.py on main acaf5f2, `_later` (:117-140), the cursor update (:608-614), `_approve_session` (`now = self.clock()`, :618+); the C-463 report (20261102-0530-reviewer-c463-pr296.md, Observation F-C463-1).

## Objections first (why not just add a bound)

1. A bound that is too tight drops real events: the host clock and the API clock disagree by some amount, and a cursor that ignores a genuine event time loses approvals (fail-open for the human, fail-closed for the agent: the session simply waits).
2. A bound that is too loose leaves the freeze in place for the inputs it was meant for (year 9999 is caught by anything; "next month" is not).
3. Ignoring a value silently hides a misbehaving upstream; with no signal the next freeze is still invisible.
4. "Previous cursor plus N" cannot cover the FIRST value (no previous cursor), which is exactly when `9999-...` arrives first.

## Proposed rule

Ignore a `processed_at` as a cursor candidate when its instant is later than `self.clock()` plus `MAX_CURSOR_AHEAD_SECONDS`, with `MAX_CURSOR_AHEAD_SECONDS = 600` (ten minutes). One new condition in the existing cursor-update `if`, next to the "is a time" test (the injectable `clock` is already on the object, so tests need no sleep):
`and _time_or_none(processed) <= now_instant + timedelta(seconds=MAX_CURSOR_AHEAD_SECONDS)`.
Naive datetimes are read as UTC by the existing `_time_or_none`; an event timestamp in the past is never affected; the cursor still only moves forward (`_later`). Why 600 s: far above NTP-managed drift (sub-second to seconds), far below anything that could be a real event time (events are server-stamped at write time, so a real `processed_at` is never in the future by more than clock skew).
Observability (one line, optional, say if you want it): a per-session counter `cursor_ahead_ignored` in the same state object as `cursor`, so a misbehaving upstream shows up in a status read instead of staying invisible (objection 3). No new setting, no env var.

## Failure conditions I checked on paper

- Host clock far behind the API (hours): real events would look "ahead" and be ignored, freezing the cursor at its old value (reads stay correct but re-read old events: duplicates, which the approver already tolerates by event id). Mitigation: the counter makes it visible; a host that far off breaks TLS first.
- First read of a session: no cursor, `processed_at` in the past: unchanged.
- An event exactly at now plus 600 s accepted; at plus 601 s ignored: pinned as the boundary.
- A year-9999 value followed by real times: cursor stays at the last real time (the F-C463-1 sequence), a real time after a garbage one still becomes the cursor.

## Test plan if you say go (tests first, one PR from main, builder Lane 11)

`services/claude-approver/tests/test_cursor_ahead_c463.py`: (a) the F-C463-1 sequence `["9999-12-31T23:59:59Z", "2026-10-28T13:00:00Z"]` leaves the cursor at the real time and the recorded `created_at_gte` never 9999; (b) boundary: now+600 s accepted, now+601 s ignored; (c) naive and aware spellings of the same instant behave the same; (d) a past time unaffected; (e) the counter, if wanted. Mutants (each red): bound removed; bound applied only when a cursor exists; `<=` made `<`; ten minutes made a day; the check applied after the store. claude-approver suite and the 16-suite GX10 run on the exact head; reviewer delta needed.

## Decision wanted from you

Go with 600 s and the optional counter? Or a different bound, or leave B-17 as an accepted limit (an upstream that stamps 9999 is outside the threat model: the input is server-set)? I will not write code until you say.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
