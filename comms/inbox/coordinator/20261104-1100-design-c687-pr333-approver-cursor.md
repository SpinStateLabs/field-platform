# C-687: read of PR 333 (claude-approver: bound the events cursor by the clock, store it normalised) at 39f8636, Lane 10

Read-only; UNVERIFIED on any estate. Probe: 20261104-1100-design-c687-cursor-time-probe.py (22 time spellings through the module's own `_time_or_none`, plus the bound), 8 own mutants, the whole approver suite.

VERDICT: PASS on 39f8636. The bound and the normalisation work and every mutant goes red; the C-438 `_later` contract is untouched and its tests pass. One new LOW-MEDIUM defect the PR introduces: a `processed_at` that parses but cannot be converted to UTC raises an unhandled OverflowError. Confidence HIGH (run).

## ASSUMPTIONS
1. The cursor is per session and in memory (state.cursor, core.py:231); the persisted `usage-cursor.json` is a different cursor (usage posting) and is not touched.
2. `processed_at` comes from the Anthropic events API; I treat it as hostile or odd input.

## Objections first
1. New failure: the normalisation `moment.astimezone(timezone.utc)` (core.py:629) raises `OverflowError` for a time that parses but whose UTC form leaves the supported range: `0001-01-01T00:00:00+05:00` (year 0001 with a positive offset) and `9999-12-31T23:59:59-05:00` (probe: both raise). The far-future one never reaches the line (it is ignored as future first), but the year-0001 one is below the bound, passes `moment is not None` and hits the conversion with no try around it in `_read_events`: the exception propagates out of the event read. The cursor is not advanced, so the same event is read again on every cycle: a poison event. Before this PR the raw value was stored without conversion, so this is a regression for an input no real API sends. LOW-MEDIUM (defensive). HIGH (run).
2. Clock skew: the bound compares `processed_at` with the APPROVER's clock plus 5 minutes (`CURSOR_FUTURE_SLACK`, core.py:112). If the approver's clock runs more than 5 minutes BEHIND the API's, every fresh event counts as "future": the cursor never advances (`cursor_future_ignored` rises on every event), and each cycle re-reads from the old cursor. Functionally safe (the same as startup, full read), but wasteful and silent except for the counter. A clock AHEAD only widens the window. MEDIUM-LOW; the slack is a constant, not a setting.
3. `wall_clock` is injectable (a constructor argument), so tests control it; in production it is `datetime.now(timezone.utc)`. A host with a wrong system clock is the real input here. INFO.
4. The date-only spelling `"2026-11-04"` (parsed as midnight UTC) and the basic format `20261104T120000Z` (parsed by Python 3.11+ `fromisoformat`) are accepted as times; a date-only value in the future of today is ignored by the bound, a date-only value of today is stored as midnight (earlier than the true event time), so `created_at_gte` could re-include events of that day: safe direction (no event is lost), more reads. LOW.
Steelman: the cursor is bounded (one year-2999 event can no longer stall the session forever), it is stored as the normalised UTC instant (padded, date-only, basic-format and offset spellings all collapse), an ignored value is counted and exposed, and the earlier contract (an unparsable value is never later than a real time) is unchanged.

## Results (the card's questions)
- Clock skew: boundary exact: `now + 4m59s` and `now + 5m` are kept, `now + 5m01s` and `now + 1y` are ignored, `now - 1y` is kept (the comparison is strict). My mutants: no slack (1 red), `>=` at the boundary (1), slack of 5 days (3), frozen clock in the past (22).
- A future cursor: `2999-01-01T00:00:00Z` and `9999-12-31T23:59:59Z` are ignored and counted; the cursor stays the last real time. A cursor already in the future cannot be created by an event any more. (A cursor loaded from disk is not involved: the events cursor is in memory.)
- Non-UTC offsets: `+02:00`, `-05:30`, `Z`, a naive time (read as UTC), padded text, a space separator, date-only and basic format all parse to the same instant and are stored as an aware UTC datetime (for a datetime input) or an ISO string in UTC (for a string input). My mutants: stored without UTC normalisation (3 red), raw value stored (15 red).
- The C-438 `_later` contract: unchanged; the C-412 guard tests that cover it pass; swapping the arguments is red (10).
- Not parsed as times (so never a cursor): an epoch integer, a float, `True`, `None`, empty, `"nan"`, Unicode digits, an offset of +24:00, a leap second `:60`: all `None`.
- The suite: the whole claude-approver suite passes (302 passed); the two touched test files 61 passed. 8 mutants: 8 of 8 red.

## Findings
F-C687-1 LOW-MEDIUM: guard the conversion: `try: utc = moment.astimezone(timezone.utc) except OverflowError: treat as not a time (count it)`; pin `0001-01-01T00:00:00+05:00` and `9999-12-31T23:59:59-05:00` as "ignored and counted".
F-C687-2 MEDIUM-LOW: make `CURSOR_FUTURE_SLACK` a documented setting or log once when `cursor_future_ignored` exceeds a small count in a window (a sustained count is a clock problem, not an attack).
F-C687-3 INFO: README says what the counter means (a sustained rise points at the approver's clock).

## What I did NOT do
Did not run the approver against the real API or a skewed host clock; skew was reasoned and bounded by the mutants. Did not read the persisted usage cursor path. Did not run the whole tools suite. Did not edit the PR.
