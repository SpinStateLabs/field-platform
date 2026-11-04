# Lane O reviewer: PR 527 (scout P-23, force-gateway tests: GET /presets and /presets/{name} over HTTP) @9b21d9ce0f2ad661ce7b0b102ae7ed8b8b657ade. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head 9b21d9ce. Lane A (force-gateway). One commit on main cd3b7690 (contains main: yes), Don Hagell noreply as author and committer (HIGH); one new test file (+83), no source change. I did not write the head. Claimed through dispatch.sh (R-PR527-9b21d9c).

Objections first: (1) one test pins behaviour the PR itself calls a finding: the 404 detail repeats the caller's name as a repr (`test_the_404_repeats_the_callers_name_as_a_repr_today`); it is labelled REPORTED, not fixed, and a later fix must change that test on purpose, which is the intent (read, HIGH). It sits against the repo's own rule that errors repeat no caller text (C-1114/C-1158), so it needs a ruling, not just a pin. (2) the route returns `PRESETS` verbatim, so any change to the table shape (a nested value) is a public API change that these tests would pin only by equality with the same dict (read, HIGH). (3) "odd name" cases accept 404, 405, 307 or 308 as passing, so a change from 404 to a redirect is invisible (read, HIGH).

Run here (cloud, scratch worktree on 9b21d9ce): new file 18 passed; whole force-gateway suite 466 passed. NOT run: the 16-suite set, CI.

Mutants on api.py and presets.py (24 run in a scratch worktree; each against the new file, survivors against the whole suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 GET /presets is the table | 4 | 3 | 1 |
| B2 GET /presets/{name} returns the name and the block | 4 | 4 | 0 |
| B3 an unknown preset is 404 naming the valid ones | 4 | 4 | 0 |
| B4 the block carries the protocol header and every component | 4 | 3 (2 by older tests) | 1 |
| B5 odd names are 404, 405 or a redirect, never a 500 or a path | 4 | 4 | 0 |
| B6 the 404 repeats the name as a repr (pinned as today) | 4 | 3 | 1 |
| Total (counted from the rows) | 24 | 21 | 3 |

Survivors (3): 1 equivalent, 2 real LOW pin gaps.
- Equivalent (read, HIGH): reversing the order of the dict returned by /presets (JSON object equality ignores key order).
- F-O-pr527-1 LOW: the "(preset: ..., components: ...)" header text: dropping the components part survives; the test checks only the title and `preset: analysis` (presets.py preset_block).
- F-O-pr527-2 LOW: the repr case: `{preset.upper()!r}` survives because the test marker `MADE-UP-MARKER` is already upper case; use a mixed-case marker.

CONDITIONS (blocking): C1 CI green on the exact head; a tests-only PR may take a light GX10 run that says "tests only" (I could not run it). C2 a ruling on objection 1 (does this route repeat the caller's name?), recorded; the test stays as the guard until then.
Optional, NEW PR only after the head is frozen: F-O-pr527-1/2 pins; tighten the odd-name status set to the one status the route gives.

Tokens/cost line: not available to me. I do not know.
