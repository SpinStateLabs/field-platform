# Lane O reviewer: MERGE 13 (batch rb-stack2: PRs 358, 359, 348, 402; main b5826200 to 32b6eaa3; 20 commits), ROLE-LOOP FALLBACK, read-only post-merge review. PARTIAL. UNVERIFIED (cloud, no GX10)

VERDICT: PASS WITH CONDITIONS (retroactive; already on main) for the CODE in packages/field-agent/src/field_agent/canary.py, liveness.py and services/ops-console/src/ops_console/api.py, naming the merged head 32b6eaa3. NOT COVERED, "I do not know": tools/tests/test_renew_token_pins_c212.py (the `renew_token` and `is_guarded` pins), the response-cap tests' "drain the request body first" change, the ENVIRONMENT.md edits beyond an anchor check, and the test files themselves (used only as the kill oracle). All 20 commits: Don Hagell noreply as author and committer (git log, HIGH). `tools/environment_anchors.py --check` on this head: 0 wrong anchor row(s) (HIGH). I claimed MERGE 13 in a note (20261104-0846) before starting; a MERGE 13 reviewer note by another session would duplicate this one.

Objections first: (1) `is_guarded_killswitch_call` is a LITERAL text match (fails closed on a different spelling by design); a client that builds the URL from the same base but with an uppercase host would silently lose its operator pair, a usability cost, not a safety one (read, HIGH). (2) the ops-console shows a 4xx upstream body on write routes (the operator needs the refusal text) but a fixed text on reads; any upstream that echoes the caller's input in a write-route 4xx still reaches the page (read, HIGH; the repo's own rule, C-763). (3) fleet-halt errors are a documented C-19 exception to "no upstream 5xx body": one line of up to 200 characters per errored agent (code comment, HIGH).

Run here (cloud, scratch worktree on 32b6eaa3, relative PYTHONPATH of every service src and packages src): field-agent the four PR test files 73 passed and the whole package suite 207 passed; ops-console the two PR test files 148 passed and the whole suite 448 passed (169 s). NOT run: the 16-suite set, CI.

Mutants (70 run in a scratch worktree on 32b6eaa3; each against the PR's own test files, survivors against the whole field-agent suite or the two modified ops-console test files; no syntax-broken kills; the unmutated baselines of those suites pass):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| G1 guard: POST only, literal base, guarded prefixes | 5 | 4 | 1 |
| G2 guard refuses dot segments (plain and encoded) | 5 | 4 | 1 |
| G3 guard refuses %, backslash, ;, controls and space | 6 | 6 | 0 |
| C1 canary reply cap: an over-cap body is never read or parsed | 5 | 5 | 0 |
| C2 error-body read failure is a transport error, connection closed | 4 | 3 | 1 |
| L1 liveness errors name the type or the status only | 4 | 4 | 0 |
| O1 _seg: one encoded path segment, dot segments encoded | 4 | 4 | 0 |
| O2 _http_status: 0 and 1xx to 3xx become 502 | 4 | 4 | 0 |
| O3 _relay: 4xx relayed, 5xx fixed text, no body logged | 5 | 5 | 0 |
| O4 _decode: non-JSON keeps its status, a 2xx non-JSON is an error | 4 | 4 | 0 |
| O5 bulk agent ids: the registry grammar only | 4 | 4 | 0 |
| O6 fleet-halt domains: non-empty, no slash | 4 | 3 | 1 |
| O7 a failed drill shows only the report fields | 4 | 4 | 0 |
| O8 fleet-halt error text cut to 200 characters | 4 | 4 | 0 |
| O9 source lines carry no upstream base URL | 4 | 4 | 0 |
| O10 usage rows: odd registry answers are unavailable, not a crash | 4 | 4 | 0 |
| Total (counted from the rows) | 70 | 66 | 4 |

Survivors (4): 2 equivalent, 2 real LOW pin gaps.
- Equivalent (read, MEDIUM): dropping the "/" from the base prefix test (`url.startswith(base)`; the guarded-prefix test on the tail still refuses `http://ks:8005x/kill/..`) and comparing dot segments without lower() (a `%` anywhere in the path is already refused earlier).
- F-O-rb2-1 LOW: the generic transport failure in urllib_call returns the exception TYPE name; a mutant returning str(exc) survives, so nothing pins that the generic branch (not the error-body branch) is type-only (canary.py, the outer except).
- F-O-rb2-2 LOW: an explicit `"domains": null` in a fleet-halt body: removing the `domains is not None` guard survives; the validator would raise TypeError (not a ValueError) on None, which pydantic does not turn into a 422 (read, MEDIUM: not run).

CONDITIONS (none blocking; on main): C1 a tests-only card for F-O-rb2-1 and F-O-rb2-2. C2 the uncovered parts above need a reader (renew_token pins, the body-drain test change, the ENVIRONMENT.md rows).

Tokens/cost line: not available to me. I do not know.
