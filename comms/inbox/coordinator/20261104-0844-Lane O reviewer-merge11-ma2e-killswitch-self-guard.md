# Lane O reviewer: MERGE 11 (batch ma2e; main b5e98d8e to 74131762; PR 336, kill-switch self-route guard and halt client; 13 commits), ROLE-LOOP FALLBACK, read-only. PARTIAL. UNVERIFIED (cloud, no GX10)

VERDICT: PASS WITH CONDITIONS (retroactive; already on main) for the CODE in services/kill-switch/src/kill_switch/api.py and its tests, naming the merged head 74131762. NOT COVERED, "I do not know": the README and FIELD_KILL_ENDPOINT_ALLOWLIST docs commits, the ENVIRONMENT.md anchor, and the removal of one line from tools/tests/http_env_proxy_allowlist.txt (consistent with the new trust_env=False, not checked against the C-57 lint). All 13 commits: Don Hagell noreply as author and committer (git log b5e98d8e..74131762, HIGH). No WORKLIST item or claim lock exists for MERGE 11 (coordinator: add a line or mark it done to avoid a duplicate).

Objections first: (1) the guard is a string check on the endpoint PATH, not on the resolved target; a host that resolves to the kill-switch itself, or a redirect (the client never follows one, so only the first hop is judged), is outside it (read, HIGH). (2) a path that is "untrustworthy" (double-encoded, dot segment, backslash, control character) is treated as self and refused, so a legitimate endpoint with such a spelling is refused too: fail closed by design. (3) I checked a suspected hole and it is NOT one: `path.casefold()` is compared with an agent id that is not case-folded, but the registry restricts agent ids to `^[a-z0-9][a-z0-9._-]*$` (agent_registry/models.py:22 and :52), and the probe `_is_self_endpoint("/kill/Agent-A", "Agent-A")` is True anyway through the "/kill/" shape (run, HIGH).

Run here (cloud, scratch worktree on 74131762, relative PYTHONPATH of every service src and packages src): test_self_guard_c574.py plus test_halt_result_c811.py 75 passed; whole kill-switch suite 235 passed. NOT run: the 16-suite set, CI.

Mutants on kill_switch/api.py (37 run in a scratch worktree; each against the three PR test files, survivors against the whole suite; no syntax-broken kills):
| Behaviour | Mutants | Killed | Survived |
|---|---|---|---|
| B1 canonical path: decode once, refuse unsafe spellings (double decode, no decode, % check, backslash, control, NUL, dot segments, slash collapse, trailing slash) | 10 | 10 | 0 |
| B2 case folded before the shape check | 3 | 3 | 0 |
| B3 every served route has a self shape (/operator/, /docs/, /redoc, /openapi.json, /health, /liveness) | 6 | 6 | 0 |
| B4 the halt client ignores the proxy environment, no redirect, timeout | 4 | 4 | 0 |
| B5 ledger gap counted, locked, on /health, logged without the message | 6 | 6 | 0 |
| B6 a 3xx answer is a failure named http_redirect | 4 | 3 | 1 |
| B7 an untrustworthy spelling is treated as self | 4 | 2 | 2 |
| Total (counted from the rows) | 37 | 34 | 3 |
B2 has 3 mutants (under 4).

Survivors (3): 1 real LOW pin gap, 2 equivalent:
- F-O-ma2e-1 LOW: the boundary status 300 is unpinned: `status > 300` instead of `>= 300` survives, so a 300 Multiple Choices answer would read as a delivery (api.py status check).
- Equivalent (MEDIUM): dropping either the `endswith("/kill/<agent>")` branch or the `"/kill/domain/" in path` branch of _is_self_endpoint survives because the "/kill/" shape matches both; each branch is dead weight next to the shape list (a LOW simplification, and it means those two branches are not independently pinned).

CONDITIONS (none blocking; on main): C1 a tests-only card for F-O-ma2e-1 (status 300). C2 the docs commits and the allowlist line need a reader; not covered here. C3 coordinator: a WORKLIST line or done note for MERGE 11.

Tokens/cost line: not available to me. I do not know.
