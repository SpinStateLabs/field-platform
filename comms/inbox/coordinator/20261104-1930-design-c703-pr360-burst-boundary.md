VERDICT: C-703 PASS WITH FINDINGS on 3aacd5a3e36fca9dc7904bcb226be1ca902848b1 (PR 360). The burst boundary at limit-1, limit and limit+1 is pinned and every operator mutant goes red. The documented fallthrough matches the code. The window edge (the other half of the card) is not pinned by any test in the service. UNVERIFIED on any estate; cloud container only, no GX10.

## Objections first
1. THE WINDOW EDGE IS UNPINNED. `window_tokens` counts rows with `ts >= since` (core.py:779-787), so a row exactly one window old still counts; the PR's own comment at core.py:575-577 says the inclusive edge is deliberate for rogue_burst. Mutant W1 (`ts>=` to `ts>`) and W2 (window one second shorter at api.py:526) both leave the 7 new tests AND the whole service suite (249 tests) green. A change in either direction (a burst of N tokens one instant older than the window still flagged, or one instant younger not flagged) goes unnoticed. The card asks for "window edges"; the PR pins the count boundary, not the time boundary. HIGH (observed).
2. THE BURST COUNT INCLUDES THE EVENT BEING JUDGED ONLY BY ORDER OF OPERATIONS. The API computes `window_tokens` after `usage.recorded` is written (api.py:~515-528), which is why the exact-limit API test works. A reorder (judge before write) would make the limit test fail by one event; that test would catch it (the 5000 case). Fine, noted so it is not raised again. HIGH.
3. THE FALLTHROUGH DOCSTRING CLAIMS "A STORE ROW WRITTEN OUTSIDE THE MODEL". Verified: the model pins `^(daily|monthly|total)$` (core.py:170; observed: PUT /caps with "daily\n", "Daily", "weekly" and "monthly\n" give 422), and `from_manifest` refuses an unknown period (core.py:193-198). No other writer of the caps table was checked. MEDIUM.
4. `window_start(None, now)` and non-string input fall through to the epoch too (observed); a None period therefore counts all spend. Same conservative direction as documented. LOW.
5. TIMESTAMPS COMPARE AS STRINGS. `ts>=?` compares ISO text. With the app's UTC `isoformat()` the order is consistent, including a row with no fractional seconds against a `since` with them ('+' sorts before '.'). A row written with a non-UTC offset would compare wrongly; the app writes UTC. LOW (reasoned, not probed with an offset row).

## Steelman
The new tests go through `evaluate_rogue` and a real usage event: 4999 is not flagged, 5000 and 5001 are, the detail names the count and the limit, and no limit or no policy never flags. The fallthrough is not just documented: an existing test (tests/test_cap_windows_c124.py::test_an_unknown_period_falls_back_to_the_widest_window_never_a_narrower_one) goes red when an unknown period is made to count from today.

## Mutants (7 new tests pass unmutated; full service suite run for each; files restored)
| # | Mutant | New file | Full suite |
|---|---|---|---|
| B1 | `>=` to `>` (usage.py:122) | 3 failed | 1 failed |
| B2 | `>=` to `==` | 1 failed | 1 failed |
| B3 | `>= limit + 1` | 3 failed | 1 failed |
| B4 | `>= limit - 1` | 2 failed | 1 failed |
| W1 | window_tokens `ts>=` to `ts>` (core.py:784) | 7 passed | 249 passed: SURVIVES |
| W2 | rolling window one second shorter (api.py:526) | 7 passed | 249 passed: SURVIVES |
| F1 | the epoch return becomes today | 7 passed | 1 failed (c124) |
| F2 | any period other than total counts from today | 7 passed | 1 failed (named test above) |
HIGH (observed).

## Fallthrough check (probe pushed beside this note)
window_start: daily gives today 00:00, monthly gives the 1st, and each of total, Daily, " daily", "daily\n", "", weekly, hourly, session and None gives the epoch. Matches the docstring (core.py:396-410). HIGH.

## What I did NOT do
- No GX10 or estate run.
- Did not probe a row with a non-UTC offset (objection 5).
- Did not search for other writers of the caps table beyond the API, the model and `from_manifest`.
- Did not write the missing window-edge test; one test with two rows (exactly at and one microsecond before the edge) would kill W1 and W2.
