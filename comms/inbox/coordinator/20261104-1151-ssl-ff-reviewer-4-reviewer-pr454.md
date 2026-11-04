# Reviewer report: PR 454 @ 616e01ed5edff68c3e66f380c4590f9a105d3e97 (C-1165, SPEC R-D4)
Reviewer: ssl-ff-reviewer-4. All runs UNVERIFIED (cloud, no GX10). Two commits on base 4f731ee9 (7836bc61 corpus+generator+README, 616e01ed tests), 5 new files under defence-shield/agent-incident-retro/ (corpus/README.md, calibration.log, labels.json, make_calibration_corpus.py, tests/test_calibration_corpus_c1165.py). Author and committer of both = Don Hagell 13129187+dhagell@users.noreply.github.com (HIGH). Merge with current main: `git merge-tree --write-tree` clean (no conflict). Additions only, no code under src/ changed (HIGH).

## Objections first
1. A corpus of 15 actors, 19 sessions, built by the same author who wrote the detector, can only characterise the detector, not validate it; the README says so (corpus/README.md "What it does not show"), but a green test may still be read as "calibrated". Counts pinned here will also fail on any legitimate detector change (intended, but it makes the file a change-detector).
2. The pinned numbers are consequences of the corpus author's scenario choices (e.g. benign actors that happen not to trip any clause): "no benign actor flagged" is true by construction of 6 hand-picked benign cases.
3. Prose in the README repeats counts the test pins in code; nothing ties the prose to the numbers (see M20, M21).

## Verified
- Baseline on the exact head: tests/test_calibration_corpus_c1165.py 30 passed (relative PYTHONPATH `src:../../packages/field-core/src`; field-core is needed for import). Whole retro suite: 258 passed, 1 failed (tests/test_cli.py::test_scan_is_deterministic_across_processes, FileNotFound, environment; identical on every mutant run, so never counted as a kill).
- Every address in calibration.log is in 192.0.2.0/24, 198.51.100.0/24 or 203.0.113.0/24 (RFC 5737), pinned by test_every_address_in_the_log_is_a_documentation_address. No estate address, flag, build id or deploy status.
- Detector checks I ran outside the tests: slow-pivot actor 203.0.113.51 is REVIEW at pivot_window_s 390 and ESCALATE at 410 and 450, so the clause sees a 400 s gap (benign request at t+30, payload at t+430), not 430 s.

## Mutants (scratch worktree on the head; baseline 30 passed subtracted: a kill = at least one failure in the corpus test file)
| # | Mutant | corpus test | whole retro suite |
|---|---|---|---|
| M1 | default pivot_window_s 300 -> 500 | KILLED (4) | |
| M2 | default session_gap_s 1800 -> 8000 | KILLED (3) | |
| M3 | default session_gap_s 1800 -> 600 | survived | killed (2) |
| M4 | S.silent-200 clause removed | survived | killed (7) |
| M5 | campaign needs 4 IPs | KILLED (1) | |
| M6 | S.marker clause removed | survived | SURVIVED |
| M7 | verdict_for: severe alone -> ESCALATE | KILLED (7) | |
| M8 | verdict_for: severe alone -> no REVIEW | KILLED (8) | |
| M9 | pivot window doubled at call site | KILLED (4) | |
| M10 | session gap boundary > -> >= | survived | killed (3) |
| M11 | pivot window boundary > -> >= | survived | killed (2) |
| M12 | cadence_cv_max 0.35 -> 5.0 | survived | SURVIVED |
| M13 | cadence_min_requests 20 -> 3 | survived | killed (2) |
| M14b | IP allowlist loop disabled | KILLED (1) | |
| M15 | generator: slow pivot 430 -> 250 s | KILLED (1) | |
| M16 | generator: poller cadence 30 -> 31 s | KILLED (1) | |
| M17 | calibration.log: one address -> non-doc address | KILLED (5) | |
| M18 | labels.json: one benign -> rogue | KILLED (3) | |
| M20 | README "15 made-up" -> "16" | survived | SURVIVED |
| M21 | README "Nineteen sessions" -> "Twenty" | survived | SURVIVED |
| M22 | README drops "no real traffic" | KILLED (1) | |
| M23 | labels.json: scanner authorized -> rogue | KILLED (2) | |

Totals counted from the table: 22 valid mutants; killed by the PR's test file 13 (M1 M2 M5 M7 M8 M9 M14b M15 M16 M17 M18 M22 M23); survived the PR's test file 9 (M3 M4 M6 M10 M11 M12 M13 M20 M21). The 9 survivors run against the whole retro suite: 5 killed by other tests (M3 M4 M10 M11 M13), 4 survive (M6 M12 M20 M21). Invalid and excluded: my first M14 (disabled only the user-agent branch, not the IP branch; replaced by M14b) and my M19 (no-op). I did not run the other 15 suites; the PR touches no shared code.

## Findings
- F-C1165-1 LOW: README prose counts (15 actors, 103 lines, Nineteen sessions) are not tied to the pinned numbers (M20, M21 survive everything). A one-line test or generating the sentence from the data would close it.
- F-C1165-2 LOW: slow-pivot wording is off by 30 s: README ("slow pivot (430 s)"), test docstring ("pivots after 430 s") vs the labels.json scenario ("after 400 s") and measured behaviour (400 s between the nearest benign request and the payload). The conclusions (REVIEW at 300 s, ESCALATE at 900 s) hold.
- F-C1165-3 LOW: not pinned by this corpus, by design: the lower side of session_gap_s (M3, caught only by other suites), the cadence thresholds (M12), S.marker (M6, which affects only attribution text at the corpus level; the G2 grade is pinned via grade_for and is separate). Optional follow-up PR; not a claim the PR makes.

## Verdict: PASS on 616e01ed5edff68c3e66f380c4590f9a105d3e97
The head is frozen; LOWs go in a NEW PR. Coordinator procedure unchanged: CI green and GX10 16/16 on this exact head rebased on current main (base 4f731ee9 is behind; the merge is clean). Not run by me: CI, GX10.
