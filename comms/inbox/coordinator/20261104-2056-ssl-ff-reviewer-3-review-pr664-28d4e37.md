# Review PR 664 @ 28d4e37566e8b612a205b5a7397833b86e382cca (incident-replay: cap a timeline summary at 300 characters with a visible marker, S4-16) - reviewer ssl-ff-reviewer-3

**VERDICT: PASS** on head 28d4e375. UNVERIFIED (cloud, no GX10); coordinator GX10 16/16 and CI on this head rebased on current main still required.

## Objections first
1. A cap that counts bytes, not characters, or cuts a multi-byte character, would corrupt non-ASCII summaries. Probed (T8, T9).
2. A silent cap hides evidence in a post-mortem; the marker with the number of dropped characters is what makes it honest. Probed (T2-T6).
3. The summary is the `str()` of the event payload (existing behaviour): a small payload still prints in full, including values; the cap bounds size, not content.

## Facts (HIGH)
- Head fetched via refs/pull/664 = 28d4e375; 1 commit; one commit behind current main (no overlap with this PR's two files); author AND committer Don Hagell <13129187+dhagell@users.noreply.github.com>.
- 2 files, +86: `incident_replay/engine.py` (`SUMMARY_MAX = 300`; `_summarize` truncates the old text, now `_summary_text`), `tests/test_summary_bounds.py` (+74, 9 tests).
- Baselines unmutated: new file 9 passed; whole incident-replay suite 106 passed.

## Mutants (the new file first; a survivor then the whole suite; file restored, clean)
| Behaviour | Rows | Killed | Survived |
|---|---|---|---|
| the cap is exactly 300 (K1, K2, K3) and the boundary: 300 unchanged, 301 marked (B1, B2) | 5 | 5 | 0 |
| a long summary is truncated, with the marker: none, no marker, wrong count (total, off by one), wording, ASCII ellipsis (T1-T6) | 6 | 6 | 0 |
| head kept, not tail (T7); characters, not bytes, for the cut (T9) and for the threshold (T8) | 3 | 2 (T7, T9) | 1 (T8) |
| the rest of the summary is unchanged (T10) | 1 | 1 | 0 |
Totals counted from the table: 5+6+3+1 = 15 rows; killed 14; survived 1 (T8).

## Survivor
- F-R664-1 LOW (T8): measuring the THRESHOLD in bytes passes. A summary of 200 two-byte characters (400 bytes, 200 characters) would then be truncated although it is under the cap; the tests have only pure-ASCII short summaries and a 400-character "é" summary that is over the cap either way. Add one 200 x "é" case that must stay unchanged.

## Conditions
None blocking. Coordinator: GX10 16/16 and CI on this head rebased on current main.
