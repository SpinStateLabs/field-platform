VERDICT: PASS WITH CONDITIONS on 39f86364de248843666524bcdf3b3985d1d6ac38 (UNVERIFIED: cloud reviewer, no GX10, CI not read; the two approver test files ran: 61 passed)

Head matches the card. One commit on main; author and committer are the no-reply identity. 4 files: claude_approver/core.py (+24 -3), README (+5 -2), new tests/test_approver_cursor_bound_c570.py (+140), tests/test_approver_refresh_guards_c412.py (+12 -?). An earlier read exists (C-628 / superseded C-665); this report is an independent probe of the cursor logic.

OBJECTIONS FIRST
1. REGRESSION, PROVEN: the new normalisation calls astimezone(UTC) on every accepted time (core.py:628-629). A time at the very bottom of the calendar with a positive offset, for example the year-1 first instant with a +05:00 offset, parses fine, passes the future check, and then raises OverflowError ("date value out of range"). The same with a datetime object. On main the raw value was stored and no such call existed. The exception escapes _read_events (called at core.py:644); a tick-level error counter exists at :519, but I did not trace what the rest of the tick does after it. The unreadable event is already in the seen set (core.py:583-585 ordering), so the next tick moves on; the cost is a lost tick for that session, not a permanent stall. LOW-MEDIUM.
2. The future bound hides up to the slack: a processed_at at the clock plus exactly 5 minutes is accepted as the cursor (the comparison is a strict greater-than, core.py:622), and the cursor goes back as created_at_gte, so events created before that instant are not requested again. A skewed or hostile value inside the slack hides up to five minutes of events. The PR documents the slack as a tradeoff; it is a bounded form of the very bug it fixes. LOW-MEDIUM.
3. The wall clock is injected (wall_clock parameter, core.py:333) and defaults to the host clock. A host clock that runs fast by more than the slack makes every real event "future": the cursor never advances and the counter cursor_future_ignored climbs. That fails toward re-reading, which is safe, and is visible in the counter; but nothing alerts on the counter. LOW.
4. The cursor stored for string input is an ISO string with an explicit +00:00 suffix; the API's accepted spelling for created_at_gte was not checked (not in source).

ASSUMPTIONS
A1 processed_at values come from the SDK as datetimes or from a mock as strings. A2 Probes ran through the real _read_events with a recording client and an injected clock fixed at a made-up instant. A3 One interpreter version.

REASONING
1. Probe table (injected clock 2026-10-28T13:00:00Z; cursor after one event; "ign" = counted as future and not stored):
   - year-1 with +05:00 offset: OverflowError (objection 1). Year-1 with Z: ok.
   - clock+5 min exactly: stored; clock+5 min+1 microsecond: ign (boundary at core.py:622 is strict).
   - date only, basic format (20261028T130000Z), space separated, naive string, naive datetime, padded string: stored as an aware UTC instant (string as ISO text with +00:00; datetime as aware datetime).
   - integer epoch, +99:00 offset, NaN: not a time, never stored, not counted.
   - sequence: 12:00Z, then 2999, then 12:30+02:00 (=10:30Z, earlier), then 12:59Z: cursor 12:00Z, stays 12:00Z (future ignored, earlier not accepted), ends 12:59Z. Never regresses; the far-future value never sticks. HIGH.
2. PR tests: 61 passed. Mutants (restored; worktree removed; nothing committed): future check removed -> 7 failed; strict > changed to >= -> 1 failed; slack 5 to 6 minutes -> 3 failed; normalisation removed (store the raw value) -> 15 failed; counter increment removed -> 6 failed. Every claimed behaviour has a red test. HIGH.
3. The _later contract (C-438): unchanged; the cursor comparison still goes through _later(processed, state.cursor) (core.py:625); a normalised stored cursor compares correctly with raw values of other spellings in the sequence probe. HIGH.
4. The year-1 overflow has no test; the PR's table of "far" values covers only the future side.
5. Diff scan: no address, SHA, deploy status or credential. HIGH.

CONCLUSION
PASS WITH CONDITIONS. The upper bound works and the normalisation is correct for every sane input; one extreme input now raises where main did not.
- C1 (non-blocking; one-line fix and test): F-C687-1 guard the conversion for out-of-range instants (treat as not a time).
- C2 (non-blocking, decision): F-C687-2 whether five minutes of possibly hidden events is acceptable, or the slack should shrink.
- C3 (non-blocking): F-C687-3 consider surfacing cursor_future_ignored in /health or an alert.

FINDINGS
F-C687-1 LOW-MEDIUM, services/claude-approver/src/claude_approver/core.py:628-629 (astimezone raises OverflowError for year-1 times with a positive offset, string and datetime forms). PROVEN. New regression against main.
F-C687-2 LOW-MEDIUM, core.py:106-111 and :622 (slack equals the hidden window). HIGH.
F-C687-3 LOW, core.py:353 counter has no consumer I found. MEDIUM.
F-C687-4 INFO, accepted created_at_gte spellings of the API not verified. 

NOT VERIFIED: what the tick does after the OverflowError beyond the counter at core.py:519; the real API's accepted time spellings; CI; the full claude-approver suite.
