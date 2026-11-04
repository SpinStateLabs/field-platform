# Lane O reviewer: MERGE 18 (batch cb26: PR 447 @0b93adcc, C-1158; main 40aec372 to b39287c1; 1 commit), ROLE-LOOP FALLBACK, read-only post-merge mutant review. UNVERIFIED (cloud, no GX10)

VERDICT: PASS WITH CONDITIONS (retroactive; already on main), naming the merged head b39287c1. Lane A (tools; the code exercised is field-core http_errors.py and nine services' 422 route). One commit adding 95 lines to tools/tests/test_422_handler_installed_c1114.py, no source change; author and committer Don Hagell noreply (git log, HIGH). Counts, identity and verdict files were checked by Lane A's C-1200 audit; that audit ran no mutants; this report does. I claimed MERGE 18 in a note (20261104-0926).

Objections first: (1) a STALE DOCSTRING on main: packages/field-core/src/field_core/http_errors.py says "Only the crosswalk service installs this so far; the other services still use FastAPI's default reply", while this batch's own source scan shows nine more services installing it (and five named in NOT_YET): the module's own description contradicts the code and the test (read, HIGH; MEDIUM-LOW). (2) the nine request cases each send ONE wrong value for ONE field; a list index in `loc` (an int) and a caller-chosen dict key are not part of the nine bodies (see survivors). (3) the source scan reads text for the string `install_validation_handler(`, so a call inside a comment or a never-called branch passes (read, HIGH; stated limit in the file's docstring).

Run here (cloud, scratch worktree on b39287c1, relative PYTHONPATH of every service src and packages src): the test file 25 passed; whole packages/field-core suite 1541 passed, 1 skipped. NOT run: the 16-suite set, CI.

Mutants on field_core/http_errors.py (27 run in a scratch worktree; each against the batch's test file, survivors against the whole field-core suite; no syntax-broken kills). The batch's file alone killed 15 of the 22 kills; 7 more came from older field-core tests:
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 the reply is a 422 with a detail list | 4 | 4 (1 by an older test) | 0 |
| B2 the caller's value is never in the reply | 6 | 5 (3 by older tests) | 1 |
| B3 the offending field name is kept in loc | 5 | 3 (1 by an older test) | 2 |
| B4 each error has only type, loc and msg | 4 | 4 | 0 |
| B5 every reason is a non-empty string | 4 | 3 | 1 |
| B6 the reason does not change with the value sent | 4 | 3 (2 by older tests) | 1 |
| Total (counted from the rows) | 27 | 22 | 5 |

Survivors (5): 1 equivalent (`str(...) + ""` on the kind: a no-op), 4 real LOW pin gaps:
- F-O-m18-1: the extra_forbidden redaction line (`loc[-1] = REDACTED_NAME`) can be removed with no test failing: it matters only when the caller's unexpected field NAME equals a name known elsewhere in the app, a case no test builds (http_errors.py, the extra_forbidden branch).
- F-O-m18-2: integer parts of `loc` (list indexes): redacting every non-string-in-known part, ints included, survives; no test has an error inside a list element.
- F-O-m18-3: a plain declared query or path parameter name: removing `names.add(param.name)` survives because model fields cover the tested cases; a route with only a bare query parameter is not tested.
- F-O-m18-4: the fixed phrase for an unlisted kind (`UNLISTED_KIND_MESSAGE`) can be emptied unnoticed (B5): no case reaches an unlisted kind in this file.

CONDITIONS (none blocking; on main): C1 a tests-only card for F-O-m18-1..4 (an unexpected field named like a known field; an error inside a list element; a bare query parameter; an unlisted error kind such as uuid_parsing). C2 fix the stale docstring in http_errors.py (a one-line docs change, own PR).

Tokens/cost line: not available to me. I do not know.
