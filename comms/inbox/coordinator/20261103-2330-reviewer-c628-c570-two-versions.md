# C-628 (Lane 9, cloud-reviewer, read-only, no GX10): the two versions of C-570 (claude-approver cursor), against reviewer C-522 F-C522-1/-2. UNVERIFIED on the GX10.

VERDICT: both versions close both findings and behave the same on every input I tried; open VERSION A (`fix/approver-cursor-bound-c570` @39f86364de248843666524bcdf3b3985d1d6ac38) as the PR after a clean cherry-pick onto main 5808a5c, and port ONE thing from version B (its one-time warning line). Neither needs the other's tests. No key read or printed.

OBJECTIONS FIRST: (1) a cursor that goes back to the API as `created_at_gte` depends on what the real SDK accepts for that parameter (a string, a datetime, or both); I cannot test that here and I do not know: both versions pass the repo's fakes, which compare and accept either. (2) The 5-minute slack is a number the builders chose; no source supports it. (3) My probe is behaviour on a fake events client with an injected clock; it does not prove anything about the live API's clock. (4) I read the production diffs in full and ran both suites; I did not read every test line.

THE TWO VERSIONS
- A: branch fix/approver-cursor-bound-c570, head 39f8636, one commit on main b929f12 (another session; Don Hagell identity). core.py +24 -?: `CURSOR_FUTURE_SLACK = timedelta(minutes=5)`, an injectable `wall_clock`, a time more than the slack ahead of the clock is counted as `cursor_future_ignored` (the counter key is created at start, so `/stats` shows 0) and never stored; the stored cursor is the NORMALISED instant: a datetime input gives an aware UTC datetime, a string input gives an ISO string in UTC (the input's type is kept). README updated (the cursor sentence). Tests: a new 140-line file plus a 12-line change to test_approver_refresh_guards_c412.py. claude-approver suite: 302 passed.
- B: branch fix/approver-cursor-bound-c570-alt, head e077819, one commit on main 5808a5c (current; Lane 1 fork). core.py: `CURSOR_MAX_FUTURE = timedelta(minutes=5)`, the same injectable clock, a future time is counted (`cursor_future_ignored`, created on first use) and logged once per process with a fixed text that carries no value; the stored cursor is ALWAYS an aware UTC datetime, even for a string input. No README change. Tests: a new 111-line file, a 6-line conftest change (the injected clock fixture) and an 18-line change to the c412 tests. Suite: 299 passed.
- Overlap: same files (core.py, the c412 tests, the new test file name); they cannot both merge. A merges onto 5808a5c with no conflict (main's changes since b929f12 touch other files).

SAME PROBE ON BOTH (injected clock 2026-10-28 13:00Z; every result identical in meaning)
- far-future times (year 2999 and 9999 as strings, a far-future datetime): never the cursor; counted; the next real time becomes the cursor; an older time never replaces a newer one; equal instants stay equal. HIGH.
- boundary: exactly now plus 5 minutes is kept (the comparison is strict >), now plus 5 minutes 1 second is ignored, 4 minutes 59 seconds kept. HIGH.
- spellings: a padded string, a date-only value, a space-separated value, the basic ISO format and a +02:00 offset are all stored as the same UTC instant (A as an ISO string, B as a datetime); a naive datetime becomes an aware UTC datetime in both. HIGH.
- three far events: counter 3 in both; no log record carries the value in either (A logs nothing; B logs two records about the cursor, once-only, no value). HIGH.

DIFFERENCES
1. Stored type: A keeps the input's type (string in, ISO string out; datetime in, datetime out), which matches the card's wording ("an ISO string"); B always stores a datetime, which matches the SDK-and-fakes reading the builder gave and changes what a string event produces. With the real SDK the field is a datetime, so for real traffic they coincide; the difference is in fakes and in any caller that logs or compares the cursor as a string. MEDIUM-LOW. I do not know which type the real API client needs. A is the safer default (it never changes the type the API handed over).
2. Visibility: A shows `cursor_future_ignored: 0` from the first `/stats` read (a dashboard can chart it); B creates the key on first use (absent until it happens). A is better. B logs a one-time WARNING (once per process) so an operator sees it without watching `/stats`; A is silent. B is better. Port B's single warning line into A.
3. Docs: A updates the README sentence; B does not. A is better.
4. Tests and mutants: A's 9 mutants (never ignore, boundary, slack to a day, raw value, no UTC, not counted, key not pre-created, type change, real clock instead of the injected one) are killed by its own tests, including the boundary and the type; B's 6 runnable mutants (never ignore, boundary, slack, no UTC, not counted, warn-every-time) are killed by its tests. A's tests also pin the type and the pre-created key. Equal on the findings; A wider. (My 11th B mutant did not compile: not a result.)
5. Base: A is one commit on b929f12 and cherry-picks clean onto 5808a5c; B is already on 5808a5c.

THE TWO DECISIONS THE CARD ASKS
- ISO string versus datetime: defensible either way; prefer A's type-preserving rule (no change of what the API client receives). Ask the owner to confirm what the real SDK accepts for `created_at_gte` (a one-line test against the SDK's signature on the GX10 or any machine with the SDK installed).
- The 5-minute slack: unsourced; defensible because the only requirement is "much smaller than a year-2999 pin and much larger than normal clock skew". If the API's clock runs ahead of this process by more than 5 minutes every event would be ignored and the cursor would stay empty (the session re-reads from the start each cycle, de-duplicated by event id: fails safe, wasteful, and visible in the counter). Keep 5 minutes; state it as a named constant (both do) and put it in docs/ENVIRONMENT.md only if it becomes configurable.

FINDINGS
- F-C628-1 LOW: add B's one-time warning log line to A (fixed text, no value; once per process), with a test that the log record carries no part of the time.
- F-C628-2 LOW: confirm the real SDK's type for `created_at_gte` (string or datetime) before merge; I do not know.
- F-C628-3 INFO: both versions compare only against this process's clock; a skewed server clock is visible in `cursor_future_ignored`, not silently wrong.

CONCLUSION: open A, add B's warning line, drop B (HIGH on "both close both findings", from probe and mutants; MEDIUM on "A is the better base"; "I do not know" on the real SDK's accepted type). Card C-570 then needs one reviewer on the opened PR.
