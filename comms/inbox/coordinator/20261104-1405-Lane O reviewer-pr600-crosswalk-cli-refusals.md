# Lane O reviewer: PR 600 (crosswalk CLI: regwatch clear and set-stale refusals, a bad manifest path is one line and exit 2) @b78674fa9e2fb7170d7ef077933bef9e84315980. UNVERIFIED (cloud, no GX10, CI not seen)

VERDICT: PASS WITH CONDITIONS, naming head b78674fa. Lane B (crosswalk). One commit, Don Hagell noreply (numeric form) as author and committer (git log, HIGH). The head is 1 commit behind origin/main 97dcfec1 (git rev-list --count pr600..origin/main); a merge was not tested. Files: compliance_crosswalk/cli.py +34/-5, test_cli_error_paths.py +124, one ENVIRONMENT.md anchor; `tools/environment_anchors.py --check` on the head: 0 wrong anchor row(s) (run, HIGH). I did not write the head. Claimed through dispatch.sh (R-PR600-b78674f).

Objections first: (1) CROSS-PR HAZARD with my PR 422 review (crosswalk `StaleStore.clear` now raises ValueError for a control-character or no-letter reviewer name, PR 422 head 2fb120e4, unmerged): this PR catches only `KeyError` around `clear(...)`, so once PR 422 lands a ValueError from the stricter name rule reaches the CLI as a TRACEBACK, which is exactly what this PR removes. The blank-name check here (`not reviewed_by.strip()`) is the old rule; the new rule lives in `clear` (read of both diffs, HIGH; I did not merge the two to run it). (2) the manifest loader's refusal prints only the exception CLASS name ("manifest unreadable (OSError)") and no path or message: safe for secrets, thin for an operator (read, HIGH). (3) the framework list is printed from `sorted(FRAMEWORKS)`; if FRAMEWORKS gains a non-string key the sort raises (read, MEDIUM-LOW; not tested).

Run here (cloud, scratch worktree on b78674fa, relative PYTHONPATH of every service src and packages src plus the tests directory): new file 29 passed; whole compliance-crosswalk suite 398 passed, 5 skipped. NOT run: the 16-suite set, CI.

Mutants on cli.py (25 run in a scratch worktree; each against the new test file, survivors against the whole suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 an unreadable manifest is one line, exit 2, class name only (OSError, ValueError, YAMLError each dropped; message echo; name dropped) | 5 | 4 | 1 |
| B2 run, suggest and pack all use the guarded loader, on stderr | 4 | 4 | 0 |
| B3 exit code 2 and one error line | 3 | 2 | 1 |
| B4 set-stale refuses an unknown framework and lists the known ones | 4 | 3 | 1 |
| B5 clear refuses an unknown framework, a blank reviewer and a missing flag | 6 | 5 | 1 |
| B6 a known framework still works, names stored as given | 3 | 3 (2 by older tests) | 0 |
| Total (counted from the rows) | 25 | 21 | 4 |
B3 has 3 mutants (under the 4 asked).

Survivors (4), all real LOW pin gaps:
- F-O-pr600-1: the class name can be dropped from the manifest refusal (`manifest unreadable: give a path ...`) with no test failing: the tests check exit code and the absence of a path or traceback, not the "(OSError)" text.
- F-O-pr600-2: an extra trailing newline (so the "one named line" becomes two) passes: no test counts lines.
- F-O-pr600-3: the list of known frameworks printed unsorted passes: order is unpinned.
- F-O-pr600-4 (the objection 1 hole): `except (KeyError, ValueError)` around `clear` passes, and so does the current KeyError-only form: no test makes `clear` raise ValueError.

CONDITIONS (blocking): C1 CI green and a GX10 16-suite run on the exact head rebased on current main; I could not run it. C2 the PR 422 / PR 600 order (objection 1) recorded: whichever lands second adds the ValueError path to the CLI and a test.
Optional, NEW PR after the head is frozen: F-O-pr600-1..3.

Tokens/cost line: not available to me. I do not know.
