# LANE O post-merge review (completes the part my MERGE 4 / cb7 report left open): PR 363 (VIDEO-SCRIPT wording and the video-script figure pin, C-590 family) @ b152e955

Verdict: PASS WITH CONDITIONS. UNVERIFIED (cloud, no GX10). Read-only mutant review of the merged batch tip b152e955 (cb7, MERGE 4, 21 commits). This report covers only PR 363: docs/VIDEO-SCRIPT.md wording (commits 703dde0c, fb98bf58, be20127a, fa4f22f7, 159c7f2b) and tools/tests/test_video_script_c590.py (+113). All of those commits are Don Hagell numeric noreply (read from `git log`). `git fetch origin main` first; b152e955 is on main; the test file and docs/VIDEO-SCRIPT.md are unchanged on main since the batch (last change 159c7f2b / fa4f22f7; `git log` shows no later commit touching them).

Objections first: (1) this is a regex over prose; passing it proves the script contains no figure the regex can see, not that the script states no unbacked number. A sentence such as "sixty services" would pass if the noun is not in NOUN. (2) The pin reads only blockquote lines and `VO:` cells; any spoken text elsewhere is invisible to it. (3) The only guard that the `VO:` cells are scanned at all is `len(lines) > 40` plus one phrase that sits in a blockquote.

Baseline (unmutated, measured at b152e955): tools/tests/test_video_script_c590.py 63 passed. Mutants edit the test file's regexes or its `spoken()` reader (the test is the product under review), plus four doc edits that inject a figure into a spoken line. Each mutant was run against the same single file, `-x`; the file and the doc were restored after each run (`git status` clean). No other test reads these files, so there is no older-test survivor check.

| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 a number word or rough quantity before a count noun | 7 | 5 | 2 |
| B2 the count and time nouns | 6 | 5 | 1 |
| B3 "a second", "a minute", "an hour" | 4 | 3 | 1 |
| B4 a multiplier (10x, times faster, -fold) | 5 | 4 | 1 |
| B5 bare time phrases (in milliseconds, within minutes) | 5 | 5 | 0 |
| B6 the kept phrase masks only the whole words "one hour" | 4 | 3 | 1 |
| B7 spoken text is the blockquotes and the VO cells | 3 | 1 | 2 |
| B8 a figure added to a spoken line turns the scan red | 4 | 4 | 0 |
| Total | 38 | 30 | 8 |

Totals counted from the table: 38 = 30+8; no invalid, no noapply.

Survivors, 8 = 7 real gaps + 1 equivalent:
Real gaps:
- B1 `half` removed from the number words: "half the tests" is missed; the sample "under half a minute" is caught by another pattern (A_TIME or FIGURE_BEFORE through "a minute").
- B2 `ms` removed from the nouns: "forty ms" is unpinned (only "30 s" and "milliseconds" are sampled).
- B3 `minute` removed from "a second|minute|hour": "in a minute" is unpinned (the sample "half a minute" is caught by the number-word pattern instead).
- B4 `times (faster)` only: "times more" and "times as" are unpinned.
- B6 the kept phrase without the leading lookbehind: "twenty-one hour" style prefixes are unpinned (only the trailing guard is sampled).
- B7 `VOX:` for `VO:`: the whole VO-cell branch of `spoken()` is dead and nothing notices.
- B7 `split("VO:", 1)[0]`: the text before the marker is scanned instead of the VO text; nothing notices.
Equivalent:
- B1 digits as `[0-9]+` instead of `[0-9][0-9,.:]*`: any digit run adjacent to the noun is matched either way.

Conditions: none blocking (docs and a docs-lint test). Optional: add `VO:`-only samples to `test_the_scan_reads_the_spoken_text` (assert a phrase that exists only in a VO cell), and samples for `half the tests`, `40 ms`, `in a minute`, `times as many`, a hyphen-prefixed `one hour`. Confidence: HIGH on counts, MEDIUM on classification. Token/cost: I do not know.
