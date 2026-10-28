# R-17 reviewer report: packages/field-agent SDK (canary.py, agent.py, federation.py mutated; field_client.py reviewed in C-102) on main 444e49b

VERDICT: 87 mutants, 75 killed, 12 survived. No fail-open defect found; the survivors are body-size guards on the canary's halt endpoint, a duplicate rule-7 guard, two heartbeat-age boundaries and three argument checks.

OBJECTIONS FIRST
1. Mutation of three of eleven modules is not a review of the SDK; `bootstrap.py`, `liveness.py`, `usage.py`, `cli.py`, `_transport.py` were not mutated and I did not read them line by line.
2. The generator makes only `if` and single-comparison mutants.
3. FieldClient rules 1-5 and the env-proxy/redirect behaviour are covered by C-102 (PR 68 PASS, merged in batch A) and are not repeated.

ASSUMPTIONS
1. Main 444e49b; field-agent suite 118 tests (17 s), three clones in parallel: canary.py 64 mutants, agent.py 4, federation.py 19. canary.py read in outline (routes, auth, `_drain`, `x3_check`). [HIGH]

REASONING
1. canary.py: 64 mutants, 56 killed, 8 survived (L169, L185, L192 x2, L194 x2, L386, L493). [HIGH]
2. LOW, F-R17-1: `_drain` (canary.py:184-197), the halt endpoint's request-body guards: `if self.headers.get("Transfer-Encoding")` forced False, `if length <= 0` forced False and `<` , `if length > MAX_BODY_BYTES` forced False and `>=` all survive. The guard that refuses a chunked or oversized body to `POST /halt` (so a half-read body does not stay on a kept-alive socket and a large body is not read) is untested. The endpoint binds 0.0.0.0 by default (canary.py:243, :480) and the only access check is the fixed header `x-field-kill-origin: kill-switch` (canary.py:12, :220), which is the compose-network exposure already recorded as F-C48-1/D-12. [HIGH on the survival]
3. LOW, F-R17-2: `x3_check` (canary.py:386) `if agent not in CANARIES:` (rule 7: X3 runs on the canary only) forced False survives. The next lines still require `rec.get("domain") == CANARY_DOMAIN` and status `active` (canary.py:391-392), so a non-canary agent outside the canary domain is still refused; a non-canary agent placed in the canary domain would pass. Defence in depth, untested. [HIGH on the survival, MEDIUM on the mitigation: read, not probed]
4. LOW, F-R17-3: remaining survivors: canary.py:169 (log-line `len(args) > 1`), canary.py:493 (`if missing:` in the x3-check CLI: unset FIELD_*_URL would not refuse; the later code would then fail on `env[...]`), agent.py:85 and :175 `time.monotonic() - self._alive_at > self._heartbeat_max_age` -> `>=` (heartbeat-age boundary, 2 mutants), federation.py:96 (`manifest` not a dict) and :105 (outbound crossing without agent_id). [HIGH]
5. Pinned (all mutants killed): the halt origin check (403 without `x-field-kill-origin`), the halted state machine and nonce, `_NoRedirect`, `is_guarded_killswitch_call`, urllib_call's auth header only for the platform call (never to the canary), the X3 sequence checks and exit codes, FederationClient fail-closed on a non-200, a non-verdict 200 and unreachable. [HIGH]

CONCLUSION
No defect. Add tests for the `_drain` guards, a non-canary-agent refusal in `x3_check` with the domain check neutralised, and the two heartbeat boundaries. Not done: bootstrap, liveness, usage, cli, line-by-line read.
