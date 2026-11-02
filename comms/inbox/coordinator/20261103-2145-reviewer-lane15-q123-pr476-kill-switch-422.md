# reviewer Lane 15: Q-123, PR 476 (C-1189, kill-switch 422s never repeat the caller's text), head 4c1465c70acf662bb6600fe4518467c8d8077f40

VERDICT: PASS on 4c1465c70acf662bb6600fe4518467c8d8077f40 (2 commits on main c356e205; head re-read with git ls-remote refs/pull/476/head at claim time and again before this note, unmoved). Local Windows run, relative PYTHONPATH (";" separated), PYTHONUTF8=1, no stdin; a scratch worktree, read-only on the PR. Not a GX10 run, CI not read, and a merge with the current main was not simulated: main has moved to 4ef319cc since the PR's base c356e205.

## OBJECTIONS FIRST (limits)
1. I did not simulate the merge onto main 4ef319cc. The change is two source lines in `services/kill-switch/src/kill_switch/api.py` (the import at :70, the install call at :382), a new test file, a guard-test edit and one ENVIRONMENT.md anchor; a conflict, if any, is the coordinator's batch check.
2. "No consumer reads the default 422 body" is a grep result (no non-test source reading an `input` key next to kill, 422 or detail), not a proof. I did not read every client of the kill-switch.
3. The guard test alone (see F-Q123-1) does not prove the handler is installed on the app that serves. The new per-service request test does.

## WHAT I CHECKED
1. The two source lines are the whole production change (`git diff` of `services/kill-switch/src`: +2). The call sits after `install_authn(app)` and before the app state setup; no route, model or status code changed. The other 422 in the file (`api.py:798`, an explicit HTTPException) is unrelated and untouched. HIGH.
2. The new tests fail without the fix: the new file run against main's source (copied out of the PR head, not added to any branch): 24 failed, 4 passed (28 cases: 4 routes x 5 bodies, plus the field-name case and the extra-key case per route). That matches the PR's "24 red on main". The 4 that pass are the declared-field-name cases, which FastAPI's default already satisfies. HIGH.
3. Mutants on the install line (`api.py:382`), against the new per-service request test (28 tests): call removed KILLED; call commented out KILLED; call on a throwaway `FastAPI()` KILLED; call in a never-taken branch KILLED. 4 of 4.
4. Mutants on the same line against the guard test `tools/tests/test_422_handler_installed_c1114.py` (26 tests): call removed KILLED; commented out KILLED; call on a throwaway app SURVIVED. 2 of 3. (My C-1151 sweep on the older guard found the commented-out case surviving; it is killed here, so main already carries a stronger scan.)
5. Suites on the PR head: kill-switch 270 passed (539 s); the guard test 26 passed; `tools/tests/test_environment_doc.py` 62 passed; `tools/environment_anchors.py --check` 0 wrong anchor rows (the one row that moved, `FIELD_KILL_ENDPOINT_ALLOWLIST` `kill_switch/api.py:293` to `:294`, matches the added import line).
6. The guard test change: `kill-switch` leaves NOT_YET and joins MEDIUM-confidence MEASURED (`test_422_handler_installed_c1114.py`), so the list only shrinks as its own docstring says. The new file name is unique (`test_422_no_echo_kill_switch_c1189.py`), which the C-1114 import-file-mismatch fix needed.
7. The Don ruling on C-1158 (a fixed reason and the offending field name, never the caller's value): a declared field is still named with a fixed reason (`loc == ["body", "operator"]`, type `string_type`, asserted per route); an unexpected key is shown as the redacted `(field)`, because its name is the caller's own text. That is the helper's behaviour, pinned by the new tests, not a gap in this PR.
8. Public safety: every value in the new test is a made-up marker; no address, mailbox, path, token or key is added. Counts only.

## FINDINGS
- F-Q123-1 LOW (guard test, `tools/tests/test_422_handler_installed_c1114.py`): a call on a throwaway app still satisfies the scan (mutant KG3). The new per-service request test kills it, so nothing is exposed for kill-switch; the gap is only for a future service moved to MEASURED without a request test. Pin (one line): require the call's argument to be the name bound to `FastAPI(...)` in that function (AST), as proposed in C-1151.

## CONCLUSION
PASS on 4c1465c7. The fix is the two lines the PR says it is, the new tests fail without it and pass with it, four of four mutants on the install call die against the request test, and the suites and anchors check are green. What a PASS does not prove: CI and GX10 on this head, a clean merge onto main 4ef319cc, or that no client parses the old 422 body. After this PASS builders do not push to the branch (head-freeze); the coordinator batches it.
