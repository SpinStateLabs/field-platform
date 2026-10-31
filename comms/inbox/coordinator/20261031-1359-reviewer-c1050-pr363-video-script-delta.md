VERDICT: PASS WITH CONDITIONS on 02d1159dedaea2116564f2be885985c767fefaf6
Card C-1050 (Lane 14, cloud read-only, UNVERIFIED until re-run; docs only). The card names head 02d1159; the PR's current head is 02d1159 (GitHub API: 4 commits, 2 files, open). Delta read: 1d15264..02d1159 (one commit). No other reviewer report names this head.

OBJECTIONS FIRST
1. The figure pin is still a pattern list. My own 29 made-up spoken phrases: 10 not flagged. Gaps that are figure claims: "scores of tests" (the plural), "a handful of events", "zero tests", "ten-fold faster", "a single keystroke", "in milliseconds", "in seconds", "nanoseconds". Not claims, so I do not count them: "every second", "no tests failed", "minutes not hours" (contrast), "in no time", "instantly". HIGH (probe run).
2. The card asks whether the pin catches a spoken count written in words. It does for number words, plurals of dozens/hundreds/thousands, "a/an" plus a time unit, and "ten times faster"/"10x"; it does not for a collective word ("a handful", "scores") or for "zero". Reason: NUM (tools/tests/test_video_script_c590.py:20-24) lists words, not a pattern for collectives.
3. Failure conditions: (a) a later edit adds "scores of checks" or "a handful of tests" to the VO and the test stays green; (b) the kept figure "one hour" is masked by a plain string replace (KEPT, :30-34), so any text containing that phrase is exempt around it; (c) the two stage directions (:122-123) still say "two keystrokes" while the VO now says "a tiny edit": fine, but the pin does not read stage directions.
Steelman: every C-937 wording finding is closed, the pin now catches all ten shapes my C-937 sibling listed, and 13 of 13 mutants of the widening die.

ASSUMPTIONS
A1 Head as above. A2 "Spoken" = blockquote and VO lines as the test defines (:29-37). A3 Cloud: no demo run, no GX10.

REASONING
1. Delta: docs/VIDEO-SCRIPT.md (4 lines: the drill timings line :79-80, the keystroke VO :133, the closing line :162) and tools/tests/test_video_script_c590.py (+29 -8). HIGH.
2. C-937 conditions: C1 (blocking, tests (3.14) green): CLOSED. REST check-runs on 02d1159: all 7 success, run id 41147054481 (tests 3.11, 3.12, 3.13, 3.14, compose-smoke, compose-upgrade-smoke, fly-image-smoke). HIGH. C2 / F-C937-1 (keystroke contradiction): CLOSED, VO now "a tiny edit" (:133); the stage directions still say "two keystrokes" (:122-123), consistent with 1200 to 12. HIGH. C3 / F-C937-2 (pin gaps): CLOSED for the ten shapes named (they are SAMPLES now, test :61-69; the new test `test_the_pattern_leaves_the_backed_figures_alone` checks five backed phrases stay clean). C4 (C-886 C2/C3): carried, owned by PR 308, 338, 340; this PR does not touch it. F-C937-3 (drill wording): CLOSED, "the drill prints the kill, heartbeat and total times" matches integration/demo/run_demo.sh:88 (kill confirmed, heartbeat, total). F-C937-4 (scope wording): CLOSED by the new closing line "Governance services that say what they enforce": 14 of 14 service READMEs carry an "Enforced vs Declared" table on main (git grep), so the claim holds; it states no count. HIGH for each.
3. Tests: tools/tests/test_video_script_c590.py 42 passed at the head. HIGH.
4. Mutants (13, each once, `-x`, restored by git checkout, tree clean): drop millions/billions; drop score; drop countless; drop rows; drop keystrokes; drop hours; A_TIME out of the scan; MULTIPLIER out of the scan; KEPT mask removed; KEPT widened to hour phrases; the `Nx` form dropped; the "times faster" form dropped; A_TIME loses hour: ALL 13 KILLED. HIGH.
5. Public safety: no estate address, hostname, flag value, build id or deploy status in the delta; commits all Don Hagell no-reply (4 of 4, author and committer). Merge: PR 363 vs main and PRs 308, 338, 340, 342 clean (git merge-tree exit 0). HIGH.

FINDINGS
F-C1050-1 (LOW, no block): the pin misses collective words and "zero" ("scores of", "a handful of", "zero", "ten-fold", "single keystroke") and bare time phrases ("in milliseconds", "in seconds"). Add them or state the limit in the test header.
F-C1050-2 (LOW): the KEPT mask is a substring replace; one phrase only today, so no harm, but it exempts text on either side.
F-C1050-3 (INFO): "Fifteen events" in integration/video/record_scenes.py waits for PR 308 (out of scope per the card).

CONDITIONS
None blocking. C1 (non-blocking) F-C1050-1. C2 (carried) C-886 C2/C3 with PRs 308, 338, 340.

NOT VERIFIED: the demo run, drill timings, the printed event count, a GX10 run (the coordinator's per the card), CI logs beyond job states.

CONCLUSION
Every C-937 condition closes at this head; CI is green on all seven jobs by run id; the widened pin survives 13 of 13 mutants and still misses collective words and "zero". PASS WITH CONDITIONS (no blocker), UNVERIFIED.
