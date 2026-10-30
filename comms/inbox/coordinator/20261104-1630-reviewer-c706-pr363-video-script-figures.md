VERDICT: PASS WITH CONDITIONS on 3b2833130eba9f07ec921438ff53fe002fb21fb0 (UNVERIFIED: cloud reviewer, no GX10, CI not read; the PR's test file ran: 5 passed)

Head matches the card. One commit on main; author and committer are the no-reply identity. Files: docs/VIDEO-SCRIPT.md (5 edits) and tools/tests/test_video_script_c590.py (+39, new).

OBJECTIONS FIRST
1. Figures remain in the script that the PR's own rule ("a number the repository cannot back or that varies by machine") would remove. Spoken in Scene 2: "kill confirmed in about forty milliseconds, verified and restored in under sixty" (VIDEO-SCRIPT.md:79-80). That is a machine-dependent timing, the same kind as the "~23 s" run time the PR removed, and no test covers it (a search finds the word "milliseconds" once). It matches the committed run log (kill 43.6 ms, total 56.3 ms), so it is a figure from one run, not a promise. MEDIUM-LOW.
2. "Twelve governance systems" (VIDEO-SCRIPT.md:162) and "seven governance services" (:60) are counts. Seven is backed by the demo ("7 services healthy", run_demo.sh:51); twelve is backed by ARCHITECTURE.md:6 on main today but conflicts with the fourteen-service count PR 337 puts there. Whichever merges second makes one of them wrong. LOW-MEDIUM.
3. The regex tests catch the exact spellings of the removed figures and several variants, but not others. Added to the script one at a time (each restored): "168 tests", "a hundred and sixty-eight tests", "1,000 tests", "15 events", "~ 23s" were caught; NOT caught: "over a hundred checks", "a test count of 168", "fifteen records", "fifteen entries", "about twenty-three seconds", "23 seconds", "about 30 s", "under half a minute", "0:23", "ninety-eight percent covered". So the guards are word-shaped, not figure-shaped. MEDIUM-LOW.
4. The run-time guard is the narrowest: it matches only a tilde, digits and "s" (the exact old spelling). A script that says "about thirty seconds" passes. LOW-MEDIUM.
5. The third test only checks that "on screen" appears in the 200 characters after the callout, which a change to the callout wording could break without any figure returning. LOW.
6. The tamper-index claim is right: the cut list now says index 0, the cue card says index 0 (CUE-CARD.md:38) and the staging script edits the first record (stage_scene4.sh:85-86), so the first record is the one that mismatches. HIGH.

ASSUMPTIONS
A1 "Figure" = any number, count, percentage, timing or duration in the spoken text or cue lines. A2 Figures backed by the repository's own demo or evidence files are acceptable; machine-dependent ones are not. A3 Probes edited a scratch copy of the script; nothing was committed.

REASONING
1. The five edits: test count replaced by "a test suite that runs on every change"; event count replaced by "read the number the run prints"; run time sentence now "varies by machine"; tamper index 2 to 0. Each revert of an edit turns the new tests red (test count back: 1 failed; event count back: 2 failed; "~23 s" back: 1 failed; index 2 back: 1 failed). HIGH.
2. Remaining figures in the script, with sources: "five hundred dollars a day" matches the demo ("USD 500/day", run_demo.sh:67); "expiring in one hour" matches the demo's token lifetime (run_demo.sh:76, a 3600-second lifetime); "ninety-six percent" matches the capstone evidence (field-agent.md:14-18); "three agents" (VIDEO-SCRIPT.md:90) not checked; "four minutes", "0:60 cut", "~5 min" prep and "~140 wpm" are production notes, not narration; "1 signed anchor holds" (:121) is the staging script's output. Machine-dependent: the forty/sixty milliseconds (objection 1). HIGH for those I checked.
3. Estate/personal scan of the diff and the files: the only addresses are loopback (127.0.0.1:8011, the console tab). No estate address, flag value, build SHA, deploy status or credential. HIGH.
4. Test design: three of five tests are regexes over the whole file; the cue-card test compares two sets of index numbers; the test reads the script at import time, so a missing file fails at collection, loudly. HIGH.

CONCLUSION
PASS WITH CONDITIONS. The edits match the card's findings and the tests go red when each edit is reverted; the guard is spelling-shaped and the script still speaks one machine-dependent timing and one repo count that PR 337 changes. Conditions, none blocking:
- C1 F-C706-1: replace the spoken millisecond figures with "measured on screen" wording (as done for the event count) or accept them knowingly (they match a committed run).
- C2 F-C706-2: reconcile "twelve" with the final service count after PR 337 (or speak no count).
- C3 F-C706-3/-4: widen the guards (any number word or digit within a few words of "tests", "events", "records", "entries", "seconds", "minutes", "percent" outside an allowlist of the cited figures).

FINDINGS
F-C706-1 MEDIUM-LOW, docs/VIDEO-SCRIPT.md:79-80 (forty and sixty milliseconds). HIGH.
F-C706-2 LOW-MEDIUM, docs/VIDEO-SCRIPT.md:162 ("Twelve governance systems") against docs/ARCHITECTURE.md:6 and PR 337. HIGH.
F-C706-3 MEDIUM-LOW, tools/tests/test_video_script_c590.py (count and event regexes miss ten spellings listed above). PROVEN.
F-C706-4 LOW-MEDIUM, same file (run-time regex: only the exact old spelling). PROVEN.
F-C706-5 LOW, same file (third test depends on a 200-character window). HIGH.

NOT VERIFIED: that the demo actually prints the event count (read, not run); "three agents"; CI; the cue card beyond the tamper line.
