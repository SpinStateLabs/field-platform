# reviewer Lane 15: C-1151, mutation sweep of this session's lint and guard files, main 05942b984e5338f56ebfd5597a57f0b9c22307a3

VERDICT: 19 survivors-or-gaps across four files, none HIGH. Hand mutants run in a scratch worktree of main 05942b98 (no push to any PR, no change to main); every mutant restored byte for byte and the worktree checked clean after each batch. Local Windows run, relative PYTHONPATH (";" separated), PYTHONUTF8=1, no stdin. Not a GX10 run.

## OBJECTIONS FIRST (limits of this sweep)
1. Hand mutants are my choice, not exhaustive; a survivor list is a floor. 21 + 4 + 27 + 20 = 72 mutants ran; 11 of those are mutants I judged likely equivalent or low-value and say so below.
2. In my chat status I first wrote "24 mutants" for environment_anchors; the correct count is 21 (3 mutants were first written with multi-line patterns that did not match a CRLF checkout, and were redone as single-line patterns, so they are counted once).
3. P04 (the `OTHER_CLIENT_PACKAGES` set) was never mutated. The commit-identity guard is not on main by file name (no `tools/tests` file with identity-guard in its name; I did not search file contents), so it is not swept.
4. Survivor pins below are proposals, not tested pins.

## tools/environment_anchors.py (tests: tools/tests/test_environment_anchors_c1116.py, 16 tests)
21 mutants: 12 killed, 9 survived.
Killed: docstring string tokens counted as code, tie-break direction, nearest-versus-first line, the last-column index, `--check` and `--fix` exit codes, duplicate-row threshold, file read without newline="", apply_fixes split, the no-code-line branch, the past-the-end branch.
Survivors:
- A06 LOW-MEDIUM (environment_anchors.py:102) `<=` to `<` on the short-row test: a row with exactly four cells after the name would index cell 4 and raise. Pin: `analyse` of a row with four cells expects kind `short-row`, no exception.
- A08 LOW-MEDIUM (:113) `!= 1` to `< 1`: a file name matching two source files is rewritten against the first. Pin: two sources with the same relative suffix give kind `file`, `new` is None.
- A09 LOW (:122) off by one at the last line of the file: only the finding kind changes (docstring-or-comment versus stale). Pin: an anchor equal to the file's last line, which names the variable in a comment.
- A10 LOW (:144) `!= 1` to `< 1`: a last cell holding the target twice would be rewritten twice. Pin: a cell "x.py:5, x.py:5" raises ValueError.
- A13a LOW-MEDIUM (:76) `parse_rows` split on `splitlines` survives while the same change in `apply_fixes` is killed: no test puts a U+2028 before a wrong anchor row and runs `--fix`. Pin: that document, `--fix` rewrites the right row.
- A15 LOW (:55) the SyntaxError fallback returning nothing: no test feeds a source file that does not parse. Pin: such a file with a text-correct anchor gives no finding.
- A01, A16, A17 probably equivalent: A01 (a bare NAME token never sits on a docstring line), A16 (rel is always set when new is), A17 (the row regex already tolerates CR). Not pinned.

## tools/tests/test_422_handler_installed_c1114.py (PR 431 guard)
Mutants on `services/sealed-ledger/src/sealed_ledger/api.py` line 273 `install_validation_handler(app)`, run against the guard test and against the per-service request test (`services/sealed-ledger/tests/test_422_no_echo_sealed_ledger_c1114.py`):
- Guard test (text scan, `CALL in source`, test file :47): 1 of 4 killed. SURVIVED: the call commented out; the call made on a throwaway `FastAPI()`; the call under `if False:`. Killed: the call removed.
- Per-service request test: 4 of 4 killed.
So the guard test alone does not prove the handler is installed on the app that serves; for the nine MEASURED services the request tests do, for the five NOT_YET services nothing does (they are named with a reason). Finding F-C1151-1 MEDIUM-LOW. Pin (one line): in `_api_files`/the parametrized test, parse the file with `ast` and require a statement-level `install_validation_handler(<name>)` call where `<name>` is the variable bound to `FastAPI(...)` in the same function; that kills all three.

## tools/tests/test_boundary_echo_lint_c505.py (58 tests; the lint lives in this file)
27 mutants: 23 killed, 4 survived.
Killed: sink spellings (Error suffix, print, echo), sources (.headers, .content, getenv), safe wrappers, comparison, tuple unpack, augmented assignment, walrus, reply-field double count, test directories, both blindness floors, allow/pending/stale/skip rules, async scope, except-as names, unparsable file.
Survivors:
- B13 LOW-MEDIUM (:255) the `extra=` keyword exemption. Pin: corpus case `logger.info("x", extra={"k": resp.text})` is not a finding.
- B15 LOW (:60) `note` removed from FIELD_KEYWORDS. Pin: corpus case `Result(note=resp.text)` is a `reply-field` finding.
- B16 LOW (:61) `warn` removed from LOG_METHODS. Pin: `logger.warn(resp.text)` is a `log` finding.
- B26 LOW, probably equivalent in real code (:141) the `except` type expression not visited: only a call inside the type expression is affected. Not pinned.

## tools/tests/test_http_env_proxy_lint_c57.py (the C-57 lint, 101 tests)
20 mutants: 19 killed, 1 survived. Killed: any trust_env value counted as safe, stream, httpx2, urlretrieve, build_opener, a non-empty ProxyHandler, client class as a value, cls()/type(self)(), type()-made subclass, functools.partial, bare Client, super().__init__, dotted subclass call, AsyncClient subclass, subclass of a subclass, plugins/ scan root, attribute alias, stale entry, new site.
Survivor:
- P21 LOW (test :329) the file floor `>= 100` lowered to `>= 1`. The boundary lint pins its floors (B18 and B19 killed); this one does not. Pin: the same `test_floors_are_pinned` shape.

## ASK
One builder card, tests only (coordinator to number): add the pins above (A06, A08, A13a, A15 first; the 422 AST pin; B13, B15, B16; P21), one commit per pin, mutant red before and after listed. Lane 17 reported 19 of 30 mutants killed on PR 432 in C-1121; this sweep is on main's merged version and does not replace that report. No push from me.
