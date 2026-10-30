# Reviewer C-739 (Lane 6): PR 361 (workflow-lint spacing/case variants) @5a58ee8 and PR 363 (VIDEO-SCRIPT numbers, C-590) @3b28331

VERDICT: PR 361 PASS on 5a58ee8d4cc9a65760591b4a190019b14fa2318e. PR 363 PASS WITH ONE NON-BLOCKING FINDING on 3b2833130eba9f07ec921438ff53fe002fb21fb0: the script no longer speaks the numbers, but `integration/video/record_scenes.py:75` still burns "Fifteen events. One hash chain. Intact." into the recording, and the pins are narrow enough that six rewordings of the same claim pass. Both PRs merge cleanly onto current main (63e91b2; the PRs' base is 5808a5c); merged result: `test_environment_doc`, `test_runbook_pins_c465`, `test_workflow_security_lint`, `test_video_script_c590`: 183 passed. Whole tools suite not re-run (PR 361 is test-only, PR 363 is docs plus one test file; no src touched). CI at my read: PR 361 `tests (3.13)`, `fly-image-smoke`, `compose-upgrade-smoke` SUCCESS, rest queued; PR 363 `tests (3.14)`, `compose-smoke`, `compose-upgrade-smoke` SUCCESS, rest queued or running. Nothing used docker (shim never called); bytecode off.

## OBJECTIONS FIRST
1. F-C739-1 LOW to MEDIUM (PR 363, PROVEN): the voice-over now says "read the number the run prints", but the recorded take overlays a caption with the old number: `integration/video/record_scenes.py:75` `("chain intact: True", "Fifteen events. One hash chain. Intact.", 3.0)`. The spoken line and the burned-in caption disagree, and the caption is the unbacked number C-538 F-C538-1..3 was about. Not touched by the PR; the test reads only `docs/VIDEO-SCRIPT.md` and `CUE-CARD.md`.
2. F-C739-2 LOW (PR 363, PROVEN by evasion mutants): the pins match only "<number words> tests|events" and `~N s`. Each of these rewordings leaves all 5 tests green: "168 passing tests", "1,205 unit tests", "a test count of 168", "Fifteen ledger events are on screen", "the run takes 23 seconds", "about twenty-three seconds". A future edit can put the numbers back in other words.
3. F-C739-3 LOW (PR 363): the run-time claim still stands elsewhere (`docs/IMPLEMENTATION.md:113` "~23 s", `docs/capstone-evidence/phase-4.md:33` "~23 s"); the PR's own header says IMPLEMENTATION.md and INTEGRATION.md disagree (~23 s vs ~30 s). Only the script was fixed; the disagreement is not.
4. F-C739-4 LOW (PR 361): the `\b` in `_DYNAMIC_KEY` is unpinned: removing it survives all 127 tests (`mygithub[format('{0}','event')]` would then be flagged, a false positive no test denies). The new "word boundary" cases (`githubx`, `inputs_x`, `myinputs`) exercise the bare-token rule, not this one.

## ASSUMPTIONS
A1. Heads as stated: `gh pr view` 361 -> 5a58ee8, 363 -> 3b28331; both one to two commits on 5808a5c. HIGH.
A2. Tamper index: the cue card and `stage_scene4.sh` edit line 1 of `tamper-me.jsonl`, so the mismatch is at index 0; `docs/capstone-evidence/phase-0.md:42` shows index 2 for a different (capstone) scenario. HIGH by reading; the on-camera take was not run.

## REASONING (HIGH)
1. PR 361 diff: `_DYNAMIC_KEY` changes from `github\s*\[\s*(?!['"])` to `github\s*\[(?!\s*['"])`. The old form let the engine back off the `\s*` so `github[ 'sha' ]` was flagged as dynamic (F-C395-1 false positive); the new lookahead holds the whitespace, so a literal key with spaces is clean and a dynamic key with spaces or any case (`GITHUB[format(...)]`, `github [format(...)]`) is still flagged. The 127 tests of the file pass.
2. PR 361 mutants (7; judge: the file's 127 tests): old regex back (2 red), IGNORECASE dropped (red), `\s*` before `[` dropped (red), lookahead `\s*` dropped (2 red), quote class single only (2 red), rule never fires (4 red): 6 RED; `\b` dropped SURVIVED (F-C739-4).
3. PR 363 diff: the "~23 s" run time, the spoken "Fifteen events", "one hundred sixty-eight tests" and the 60-second cut's "index 2" are replaced; the new test file has 5 tests (5 passed).
4. PR 363 mutants (4 revert + 7 evasion; judge: `test_video_script_c590.py`): the 4 reverts RED (run time, events, tests, tamper index; "Fifteen events" back reds 2 tests); the "on screen" phrase moved beyond 200 characters RED; the six evasion rewordings in F-C739-2 SURVIVED.
5. Remaining spoken numbers the pins do not cover: "seven governance services", "Twelve governance systems", "about forty milliseconds", "under sixty" (`VIDEO-SCRIPT.md:60, 79-80, 162`). I did not verify them against a measurement here: not in source.

## FINDINGS
- F-C739-1 (PR 363): make the recorder caption not state a count (or have it read the count from the run), and add `record_scenes.py` to the pin.
- F-C739-2 (PR 363): widen the pins (any digit or number word within a few words of `test(s)`, `event(s)`, `seconds`).
- F-C739-3 (PR 363): reconcile or drop "~23 s" in IMPLEMENTATION.md and phase-4.md (a decision for the owner of those docs).
- F-C739-4 (PR 361): add `${{ mygithub[format('{0}','event')] }}` to the clean cases or accept the unpinned `\b`.

## What I did NOT do
- Wait for CI (mostly queued), run the video take or the demo, re-run the whole tools suite, or run docker, merge or deploy.
