# RED TEAM: addendum, main d6db6930 (92 commits since 41afda50). ssl-fp-red-team, 2026-11-07
Stage 2 NO-BLOCKER and Stage 3 (no code blocker) STAND on d6db6930. HIGH on code.

## Delta in the Stage 2 path (3 source files), reviewed and tested
- `operator_auth.py` (3dde4428, S8-3): `operator_headers` validates `FIELD_OPERATOR_KEY` and the operator id like the key-file path; a bad value sends NO operator headers and logs the variable name only. Fails to no-credential (a 401, never an open path). 
- `kill_switch/api.py` (bb2f236d, S4-4): `operator` max 200 and `reason` max 1000 characters, blank values refused (422); allowlist host names lower-cased (matching stays exact); heartbeat id bounded to 128 characters and no control characters.
- `agent_registry/api.py` (17777c61): comment only.
- Re-run on d6db6930 (HIGH): real 3-process Stage 2 stack, 83 probes: 3 non-passes, all known (S9 harness artifact; X1, X2 = N-1, registry LOG-ONLY at Stage 2). E4 (a 200 echoing caller text) no longer shows: the 422/echo work landed. 728 tests passed (operator_auth, rt1 headers and reserved keys, G22 gate, authn, the whole kill-switch suite, stage controller). No stale servers (0 uvicorn before the run).

## New non-blocking finding (a safety control that can now answer 422)
- RT-KS-LEN LOW/MEDIUM, HIGH: the kill-switch now refuses (422) a halt whose `reason` is over 1000 or `operator` over 200 characters. Callers that build the text can exceed it: `lifecycle decommission` sends `"lifecycle decommission: {reason}"` with a CLI-supplied reason (a long reason makes the kill step fail; the report shows `killed: false`, visible, not silent), and ops-console `/kill` and bulk models accept unbounded `reason` and `operator` and forward them, so a human who pastes a long incident note gets a 422 at the kill-switch instead of a halt. During an incident a refused halt costs a retry, not safety (the failure is explicit). Suggest the console and lifecycle models carry the same max lengths (a clear 422 before the proxy), or truncate the lifecycle text. Not a Stage 2 blocker: Stage 2 callers are `don` through curl or the console with short text.

## Unchanged conditions
Same four conditions as 20261107-0100 (hash 2 of 2 via `phase_g_check --stage 2`, build sha and service list passed to the controller, go sentence states registry LOG-ONLY and the 401s, arm then rehearse R-1 and rollback). Three manifests still lack `don-admin`: compliance-crosswalk, conformance-sentinel, force-gateway.
