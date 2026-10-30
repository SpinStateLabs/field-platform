VERDICT: C-706 PASS WITH FINDINGS on 3b2833130eba9f07ec921438ff53fe002fb21fb0 (PR 363). The three named figures are gone and the tamper index now agrees with the cue card. One spoken timing remains (script lines 79-80) that no file in the repository backs, and the new test cannot see it. No estate address, flag value, build SHA or deploy status in the script (scan below). UNVERIFIED on any estate; read-only.

## Objections first
1. A MEASURED-SOUNDING TIMING IS STILL SPOKEN AND UNSOURCED. docs/VIDEO-SCRIPT.md:78-80: "kill confirmed in about forty milliseconds, verified and restored in under sixty." The demo prints the measured values (integration/demo/run_demo.sh:86-88: `kill_confirmed_ms`, `heartbeat_confirmed_ms`, `total_ms`) and nothing in the repository states forty or sixty (grep over .md, .py and .sh: only the script itself). The PR removes "~23 s" because the docs disagree; the same reasoning applies here with less cover, since this one is read aloud as a measurement. The card asks for "any remaining figure, count or timing". HIGH (observed: two grep hits, both in the script).
2. THE TEST'S PATTERNS ARE NARROW. tests/test_video_script_c590.py checks only `<number> tests`, `<number> events` and `~N s`. Probe (patterns copied from the test): "Fifteen events." caught; "fifteen records", "a dozen events", "fifteen audit events", "15-event chain", "168 passing tests", "168 test cases", "about 23 seconds", "23s" and "half a minute" all pass. Because the script is a blockquote with a "> " prefix on each line, "fifteen\n> events" also passes. So a re-introduced count survives by rewording or by a line break. HIGH (observed).
3. OTHER SPOKEN FIGURES THAT ARE SOURCED BUT HARD-CODED. All checked against files: "seven governance services" (run_demo.sh:51 prints "7 services healthy"), "five hundred dollars a day" (run_demo.sh:67), "expiring in one hour" (`--ttl 3600`, run_demo.sh:76), "ninety-six percent" (integration/demo/README.md:30; docs/INTEGRATION.md:241), "Twelve governance systems" (README.md:43 "The 12 systems"), "1 signed anchor" (CUE-CARD.md:18). They match today; each drifts silently if the demo changes, and none is pinned by the test. MEDIUM.
4. "SEVEN SERVICES" AND "TWELVE SYSTEMS" SIT SIDE BY SIDE with 14 service directories in the repository (README.md:28: 14 directories, the 12 systems plus ops-console and claude-approver). A listener cannot tell they count different things. LOW.
5. THE DEMO URL IS LOOPBACK (127.0.0.1:8011, script lines 25, 90). Not an estate address. HIGH.

## Steelman
The PR's own goal (card C-590: no test count, no event count, no hard-coded run time) is met for exactly those three: the script now says the event count is "on screen", the 60-second cut says `TAMPERED at index 0` like the cue card (CUE-CARD.md:38), and the test also pins that the cut and the card agree. Percent, dollar and service figures are demo-defined and backed.

## Figures remaining in the script (all spoken numbers found by a word-and-digit grep)
Title "four minutes" and scene times (the script's own plan); "four invoices", "the fifth draft", "three-agent" dashboard; the figures in items 1 and 3 above; "1200 to 12" (a keystroke instruction). Only item 1 has no backing file. HIGH on the list (grep), MEDIUM on completeness.

## Public-safety scan of the script
Regex for IPv4 other than the loopback demo URL, 7-40 hex strings, home paths, webmail, deploy phrases and hostnames of tunnel or platform domains: no hits. HIGH on the scan, MEDIUM on completeness.

## Recommended
Replace lines 79-80 with "read the drill timings the run prints", as the PR did for the event count; widen the test to any number word or digit within a few words of tests, events, records, milliseconds or seconds, and join wrapped blockquote lines before matching.

## What I did NOT do
- Did not run the demo; the printed timings and event count are not measured here.
- Did not verify "four invoices" or "three-agent" against the agent fixtures.
- Did not read the cue card beyond the lines cited.
