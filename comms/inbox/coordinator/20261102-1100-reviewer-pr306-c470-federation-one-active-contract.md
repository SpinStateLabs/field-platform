VERDICT: FAIL on b30501c9c5114169f1e940d749df52375193fc66

PR 306 (builder Lane 2, card C-470, reviewer C-355 F-C355-2/-3/-4), Lane 7, no review card existed (claim note 20261102-1040). Head confirmed by PR read: b30501c, one commit (cherry-picked here as bf63120), base 613ab50 = current main; applies clean. A FAIL applies to this SHA only. Production change in services/federation-broker (engine.py, api.py), README, demo.sh and a new test file.

Why FAIL, in one line: the demo script this PR rewrites to "assert every verdict" exits 1 at step 3 and never reaches its new assertions; the PR body says the demo was not run. The production change is sound and matches PR 300's.

TWO PRS FOR ONE FINDING (decide first): PR 306 (C-470, Lane 2) and PR 300 (queue C-480, "C-461" in its title, Lane 3; my verdict PASS WITH CONDITIONS, 20261102-0830-reviewer-pr300-c461-federation-one-active-contract.md) both implement reviewer C-355 F-C355-2/-3/-4. They conflict in all four shared files (git merge-tree of the two heads: README.md, demo.sh, api.py, engine.py). Only one can merge. My recommendation: take PR 300, whose demo runs to completion, and port from PR 306 the two tests listed under "Worth keeping" below.

OBJECTIONS (before evaluation)
1. A shell script under `set -euo pipefail` that drops `|| true` from a step whose command exits non-zero on the expected result aborts.
2. An in-process test of the same sequence cannot see an exit code of a command-line tool, so it does not stand in for the demo.
3. A uniqueness rule on an exact org string is bypassed by spelling; a check done as SELECT then INSERT is not atomic across processes; legacy duplicates resolve silently (all three are my PR 300 findings; they apply here too).
4. Two PRs for one card collide.

ASSUMPTIONS
A1. `fedbroker crossing` exits 0 on ALLOW and 1 on any other verdict: cli.py:138 says "exit 0 ALLOW, 1 BLOCK (or a refused request)" and cli.py:162 raises `typer.Exit(code=1)` (HIGH, read).
A2. demo.sh runs under `set -euo pipefail` (line 3) (HIGH, read).

REASONING
1. The demo, run for real: `bash demo.sh` on loopback (ports 8002 and 8010 in this container, the venv the script expects linked temporarily, removed afterwards), source of this head on the path. Output: step 1 registers, step 2 prints "ALLOW", step 3 header prints, then the script stops: exit 1 (PROVEN). Cause: step 3 asks for customer PII, the verdict is BLOCK, the CLI exits 1, and this PR changed `... | show || true` to `... > "$WORK/overreach.json"` with no tolerance for that exit code, so `set -e` ends the script before the assertion that follows. Step 3b (keyless BLOCK) has the same shape and is never reached. The same demo on PR 300, which keeps `|| true` before each BLOCK assertion, runs to the end (exit 0) and its three mutants all fail the script (my PR 300 report).
2. The PR body says: "The demo script itself was not run ... `bash -n` passes, and the same sequence ... is a test, `test_the_demo_sequence_...`". That test (tests/test_contracts_c470.py:141-) drives the app in-process and reads JSON verdicts; it never runs the CLI, so it cannot see the exit code. CI cannot see it either: CI on this head is 7 of 7 success and the demo is not part of CI (my run is the first run of it) (HIGH).
3. The production change, read against PR 300: `save` refuses a second ACTIVE contract for the org under another id (`DuplicateActiveContract`, 409 with the other id named), same-id re-registration replaces, inactive skip the check, `for_org` orders by contract_id. Same behaviour as PR 300. Differences: the exception name; the check query has no ORDER BY; PR 306 pins both insert orders for legacy rows and a "refused write changes nothing" test (HIGH).
4. Tests: federation-broker suite on main 613ab50 plus the commit: 111 passed (95 plus 16 new). Whole `python -m pytest -q tools/tests` in a CI-style venv (pip pinned, constraints files): 2989 passed, 6 skipped, 0 failed (715 s). CI on the exact head: 7 of 7 success.
5. Mutants (hand, 11, whole broker suite): 10 red / 11. Red: guard on always, guard inverted, guard removed, self-exclusion dropped, inactive rows counted, `for_org` ORDER BY dropped, ORDER BY DESC, 409 as 400, message hides the other id, the keyless guard moved after the scope check. Survivor: `DuplicateActiveContract(ValueError)` base class changed to `Exception`: equivalent (only the API catches it).
6. Probes (made-up orgs, temp database), same as PR 300: with an active contract for "Borealis Example Corp", `save` ACCEPTS a second active contract for "borealis example corp" and for "Borealis Example Corp " (trailing space): the one-per-org rule is by exact text (PROVEN). The race and the silent legacy duplicates are structurally the same code as PR 300's (no unique index, SELECT then INSERT, no log line); I did not re-run those two probes on this head (MEDIUM, same code).

FINDINGS
- F-PR306-1 MEDIUM (PROVEN, blocking): demo.sh aborts at step 3 (exit 1), and step 3b is never reached. services/federation-broker/demo.sh, the lines that now read `fedbroker crossing ... > "$WORK/overreach.json"` and `... > "$WORK/keyless.json"`. Fix: tolerate the exit code on BLOCK steps (`|| true` followed by the assertion, as PR 300 does), run the demo to the end, and say so in the PR text.
- F-PR306-2 LOW (process): a claim of "asserts every verdict" for a script that was not run. And the in-process test named after the demo cannot stand for it. Fix: run it once on a host with the venv and ports, or add the CLI exit-code behaviour to a CLI test (typer's CliRunner against the app).
- F-PR306-3 LOW-MEDIUM, F-PR306-4 LOW, F-PR306-5 LOW: the same three gaps as PR 300 F-PR300-1/-2/-3 (spelling variants get a second active contract; no unique index and SELECT-then-INSERT; legacy duplicates resolve silently by text order). Whichever PR merges needs them closed once.
- Worth keeping from this PR if PR 300 is taken: the legacy-rows test in both insert orders (test_contracts_c470.py:92-98) and the "refused write changes nothing" test (:70).

CONCLUSION: FAIL on b30501c9c5114169f1e940d749df52375193fc66 because the demo it rewrites does not run to completion (proven by a run), and it duplicates PR 300, which does run. The engine and API change is correct (10 of 11 mutants red, the survivor equivalent, whole tools suite 2989 passed, CI 7 of 7). A one-line fix to demo.sh would turn this into a PASS WITH CONDITIONS on the same footing as PR 300, but there should be one federation PR, not two. Coordinator also needs GX10 16/0 on whichever head is chosen.

What I did NOT do
- Not run on the GX10 (cloud session); the demo ran on loopback in this container only, Python 3.13; other Pythons only through CI.
- Did not read Lane 2's builder note (20261102-0600-builder-lane2-c465-c468-c470.md) beyond its name, so I do not know why two lanes took this finding.
- Did not re-run the race and legacy-duplicate probes on this head (same code as PR 300).
- Did not examine the 6 skipped tests.
