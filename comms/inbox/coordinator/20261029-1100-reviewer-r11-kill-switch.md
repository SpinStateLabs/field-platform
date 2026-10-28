# R-11 reviewer report: services/kill-switch read and mutants (main 444e49b)

VERDICT: kill, domain kill, revive and the retired-agent guards are pinned (59 of 67 mutants killed). The drill's own failure detection is not: a drill can report success while the heartbeat still shows the agent live, and no test notices.

OBJECTIONS FIRST
1. My generator only makes `if` and single-comparison mutants: 59/67 is not a coverage figure; `store.py` produced 0 mutants.
2. I read `kill_agent`/`_kill_one`, `drill`, `set_status_on_behalf`, `_is_self_endpoint` and the endpoint status check; I did not read `kill_domain`, `revive`, `liveness` or `cli.py` line by line.
3. A surviving mutant in a branch that raises 500 may still be caught by a caller's own check (not probed).

ASSUMPTIONS
1. Main 444e49b, three clones, kill-switch suite 143 tests (8 s), `TESTS_ONLY=tests`, cwd services/kill-switch. api.py 864 lines mutated in two halves (1-430: 18 mutants; 431-864: 49). [HIGH]

REASONING
1. Results: api.py 67 mutants, 59 killed, 8 survived; store.py 0 mutants. [HIGH]
2. MEDIUM, F-R11-1: `drill` (api.py:769-864). `if kill_confirmed is None:` (L809) and `if not hb.killed:` (L813) forced False both survive. The first is the "kill did not propagate" 500, the second the "heartbeat still live" 500. With L813 off a drill continues, signals the endpoint, and returns a 2xx DrillReport with a `heartbeat_confirmed_ms` although the heartbeat never showed killed: the exact failure a drill exists to catch (a halt that does not reach the heartbeat) reports as a pass. The `finally` restore still runs. No test makes the heartbeat stay live or the registry not flip during a drill. [HIGH on the survival, MEDIUM on the reachability: depends on a registry/heartbeat fault I did not inject]
3. LOW, F-R11-2: `_signal_endpoint` (api.py:479) `status >= 400` -> `>`: an endpoint answering exactly HTTP 400 would be recorded `called`, not `failed/http_error`; boundary untested. `_is_self_endpoint` (api.py:308) first clause (`endswith(/kill/<agent>)` or `/kill/domain/` in the path) forced False survives: the later `_SELF_PATH_SHAPES` test may cover the same inputs (equivalence not probed); that function is the guard against registering the kill-switch as its own halt endpoint. [HIGH on survival]
4. LOW, F-R11-3: api.py:275 `if not raw:` (`_parse_method`, empty method), api.py:425 (`if not endpoint`, already `pragma: no cover`, the schema enforces it), api.py:532 `if previous != "killed":` forced True (an idempotent re-kill flips the registry again instead of skipping the PATCH; harmless but untested), api.py:761 `last_seen >= cutoff` boundary in `/liveness`. [HIGH]
5. INFO: `set_status_on_behalf` (api.py:223-243) calls a registry object whose class overrides `set_status` WITHOUT the C-12 on-behalf header (documented in its docstring for test doubles); a production wrapper subclass would silently lose attribution. [HIGH on the code, LOW on any live subclass: none seen]
6. Pinned and sound: retired agents cannot be flipped to killed or drilled (409 branches killed), registry-unreachable 502 branches, 404 not-registered, `_check_authorized_operators` calls, the restore-in-`finally` path and the `kill.drill.restore_failed` ledger note, the C-19 500 on a failed restore. [HIGH on mutants]

CONCLUSION
Add two drill tests (heartbeat stays live: expect 500 and restore; registry does not flip: expect 500) and boundary tests for HTTP 400 and `/liveness`. Not done: `kill_domain`, `revive`, `cli.py` and arithmetic/argument mutants.
