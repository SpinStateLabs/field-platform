VERDICT: PASS WITH CONDITIONS on 380bc30b70df68b11634ca3839b212b678e18ccb  (UNVERIFIED: cloud reviewer, no GX10, no demo run, CI not read)

C-886, PR 363 (docs: VIDEO-SCRIPT figures) at builder Lane 11's newest head (C-830), against my C-706 and C-755 (both PASS WITH CONDITIONS on 3b28331) and Lane 6's C-739. Head 380bc30 is one commit after 3b28331; two files (docs/VIDEO-SCRIPT.md, tools/tests/test_video_script_c590.py; +88 -7). This SHA only.

OBJECTIONS FIRST
1. The earlier conditions are closed in the script: F-C706-1 and F-C755-1 (the "forty" and "sixty milliseconds" spoken figures) are replaced by "the drill prints how long the kill took ... Read the figures on screen." (VIDEO-SCRIPT.md, the line block near 79); F-C706-2 and F-C755-2 ("Twelve governance systems") is now "Governance for every service" (near line 162); "Fifteen events" in the callout is now "The event count is on screen: read the number the run prints"; the "~23 s" run time is now "the run time varies by machine". Confidence HIGH (diff read).
2. The test guard is wider but still misses plural rough quantities and some nouns, which was F-C706-3, F-C706-4 and F-C755-3's point. I re-introduced variants into the script and ran the PR's test file (21 tests): CAUGHT (red): the original forty/sixty milliseconds, "Twelve governance systems", "Fifteen events", a run time of 23 s, "a hundred and sixty-eight tests", "about 170 automated tests", "well over a hundred tests", "1,000 checks", "168 tests", "one-sixty-eight tests", "a few hundred tests", "fifteen-event chain", "a dozen systems", "within two seconds", "about thirty seconds", and a tamper index changed back to 2. MISSED (green): "dozens of tests", "hundreds of tests", "thousands of events", "a lot of tests", "countless checks", "nine controls", "in under a second". Eleven re-introductions caught for each of the first group; seven misses. The builder's note says the pin is figure-shaped (a digit, number word or rough quantity next to a count or time noun); the plural rough quantities and the noun `controls` are outside it. Confidence HIGH (observed). LOW-MEDIUM: each is a figure the demo may not back.
3. Figures still in the script after the change (scan of the file for a digit or number word next to a count or time noun): "four minutes" (the title), "~5 min" prep, "one hour" (the token lifetime: backed, run_demo.sh:76 passes `--ttl 3600`), "ninety-six percent of cap" (backed: integration/demo/agent/invoicing_agent.py comments name the 96% escalation of the fifth draft), "60-second cut" (a format name). No unbacked count or run time remains in the spoken text by this scan. Confidence MEDIUM (regex scan, not a read of every line).
4. The 60-second cut now says `TAMPERED at index 0` (it said 2), to equal integration/video/CUE-CARD.md:38 ("hash mismatch at index 0"); the new test ties the two documents to each other. docs/VIDEO-SCRIPT.md:123 also says index 0. docs/capstone-evidence/phase-0.md:42 (a recorded earlier run) shows index 2. Which index a real demo run prints is not checked by anything here: the test compares two documents, not the demo. UNVERIFIED (needs a run).
5. Out of scope, named in the PR text and still true on this tree: F-C739-1: integration/video/record_scenes.py:75 burns "Fifteen events. One hash chain. Intact." into the recording (a spoken count that this PR removed from the script; PR 308 holds the file); F-C739-3: "~23 s" remains in docs/IMPLEMENTATION.md:113, docs/capstone-evidence/phase-4.md:33 and STATE.md (PRs 338/340). The script and the recording script now disagree on the event count until PR 308 is fixed. Confidence HIGH.
6. Commits: two, author and committer Don Hagell no-reply. No address, estate value, flag value or deploy status in the diff.

ASSUMPTIONS
A1 Card scope: each earlier condition (C-706, C-755) closed or not; any figure or timing left in the script. A2 A figure counts as "left" if a count or time appears in spoken text without a backing in the repository.

REASONING / CHECKS
- Tests: tools/tests/test_video_script_c590.py 21 passed.
- Mutation by re-introduction (each restored; scratch tree removed; nothing committed): 18 variants, 11 caught in the first group, 7 missed (objection 2).
- Conditions: C-706 F-1, F-2 closed; F-3 and F-4 (guard misses) partly closed (see 2); F-5 (a 200-character window in the third test) not re-checked. C-755 F-1, F-2 closed; F-3 partly closed.

CONDITIONS
C1 (non-blocking) Add plural rough quantities ("dozens", "hundreds", "thousands", "a lot of") and "controls" to the figure pin, or state them as accepted.
C2 (non-blocking) Decide whether a test should run the demo (or read its output fixture) to back the tamper index, rather than compare two documents.
C3 (coordinator) Card the recording script's "Fifteen events" (PR 308, F-C739-1) and the "~23 s" figures (F-C739-3), so the spoken and recorded versions agree.

NOT VERIFIED
GX10, CI, a demo run (tamper index, event count, timings), the rest of docs/ outside VIDEO-SCRIPT.md, F-C706-5's window.

CONCLUSION
The four spoken figures I named are gone from the script and replaced by on-screen readings; the guard catches the originals and most variants but not plural rough quantities. The recording script and some docs still carry the removed figures. PASS WITH CONDITIONS, none blocking. UNVERIFIED.

CORRECTION: objection 2 and the CHECKS line gave wrong tallies ("eleven ... caught", "18 variants, 11 caught"). The count is: 23 variants run in total, 16 caught (the sixteen listed under CAUGHT, including the tamper index change) and 7 missed (the seven listed under MISSED).
