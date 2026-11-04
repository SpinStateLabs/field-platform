# Lane O reviewer: PR 492 (S-B1, force-gateway telemetry correction regex + analyze tests) @389eeca6b9d597460c026f7977480e29aba1cc68. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 389eeca6. Lane A (force-gateway). One commit on main cd3b7690 (contains main: yes), Don Hagell noreply as author and committer (HIGH). I did not write the head.

Objections first: (1) the PR text says "one positive and one negative per marker"; that holds per marker, not per alternative inside a marker (survivors below), so the new tests pin less than the claim. (2) the regex has no trailing word boundary: "The value that is incorrectly set" counts as a correction (probe, run, HIGH). Pre-existing shape (the old regex had no trailing boundary either), so not a regression, MEDIUM-LOW. (3) these are surface heuristics (module docstring); widening the apostrophe forms changes the dashboard counts for text already in the ledger, so before/after figures are not comparable (general reasoning, MEDIUM).

Run here (cloud, relative PYTHONPATH of every service src and packages src): new test file 18 passed; whole force-gateway suite 466 passed, matching the builder. NOT run: the 16-suite set, CI.

Mutants on telemetry.py (38 written; 2 did not apply (string split across lines) and are excluded; 34 run, scratch worktree on the exact head, each against the PR file, survivors against the whole service suite):
| Behaviour | Mutants run | Killed | Survived |
|---|---|---|---|
| B1 "That's incorrect" forms (old regex, single space, curly dropped, straight dropped, incorrect-to-correct, case) | 6 | 6 | 0 |
| B2 other correction phrases (premise, correction:, not accurate, drop "false", drop "not correct") | 5 | 3 | 2 |
| B3 confidence tags (bold, bracket, LOW, has_tags >1, MEDIUM bold) | 5 | 3 | 2 |
| B4 flattery (great, excellent, clean flag, happy to help, certainly!) | 5 | 2 | 3 |
| B5 cot structure (and-to-or, no multiline, drop conclusion, drop reasoning, unanchored conclusion) | 5 | 3 (1 by older tests) | 2 |
| B6 objection markers (would break, failure, objection, drop "scenario") | 4 | 3 | 1 |
| B7 source honesty (four phrases) | 4 | 4 | 0 |
| Total (counted from the rows) | 34 | 24 | 10 |
Of the 24 kills, 23 are from the PR file and 1 (no-multiline) from older tests.

Survivors (10), all LOW real pin gaps, none equivalent:
- F-O492-1: correction alternatives "the premise is false" and "this is not correct" unpinned (2).
- F-O492-2: a single confidence tag (has_tags threshold) and "**MEDIUM**" unpinned (2).
- F-O492-3: flattery "excellent question", "happy to help", "certainly!" unpinned (3).
- F-O492-4: cot: a text missing only REASONING, and an unanchored "CONCLUSION:" mid-line, unpinned (2).
- F-O492-5: objection "failure scenario" unpinned (1).

Builder note, confirmed by read: _SOURCE_HONESTY "i don't know" and _FLATTERY "i'd be happy to" still miss the curly apostrophe (telemetry.py), out of scope for this PR.

CONDITIONS (blocking): C1 CI green on the exact head and a GX10 run of the full set (code PR; I could not run it). C2 none other.
Optional, NEW PR only after the head is frozen: F-O492-1..5 pins; a trailing \b on the correction phrase (objection 2); curly-apostrophe follow-up for the two other markers.

Tokens/cost line: not available to me. I do not know.
