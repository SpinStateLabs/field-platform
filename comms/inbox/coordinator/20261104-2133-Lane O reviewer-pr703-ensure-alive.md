# LANE O review: PR 703 (field-agent S6-4: ensure_alive clears the liveness stamp before it asks) @ f08a4df3

Verdict: PASS. UNVERIFIED (cloud, no GX10). Head f08a4df3, 1 commit on top of main, Don Hagell numeric noreply (author and committer). Source +3 (one assignment and a comment) in packages/field-agent/src/field_agent/agent.py, tests +109. Freshness: I ran `git fetch origin main` first; main = ebb027a2 (my earlier stale-ref error is corrected in the stale-main report). Head is 3 behind main, 1 ahead; `git merge-tree --write-tree` is clean. (An earlier look at this PR against a stale main showed two extra docs commits; those are main's #539 and are not part of this PR.)

Objections first: (1) the fix clears the stamp for every `ensure_alive()`, including a successful one, so a concurrent `check()` or `cross()` on another thread that arrives between the clear and the heartbeat result forces its own heartbeat; one extra call, no halt-gate hole, but thread safety is not tested and not claimed. (2) The tests replace `agent.heartbeat` with a script, so the test never exercises `ensure_alive` against a real `Liveness` client; `HeartbeatUnreachable` is raised by the script, not by a transport failure. (3) The stamp uses `time.monotonic`; the test patches `agent_mod.time.monotonic` module-wide for the test's duration, so a mutant using `time.time()` is caught only because of that patch (it was killed).

Baseline (unmutated, measured): packages/field-agent suite 214 passed (`-x`). Survivor check ran the whole field-agent suite.

| Behaviour | Mutants | Killed (file) | Killed (older only) | Survived |
|---|---|---|---|---|
| B1 the stamp is cleared before the heartbeat is asked | 6 | 6 | 0 | 0 |
| B2 a killed heartbeat raises AgentKilled and leaves the stamp cleared | 4 | 3 | 1 | 0 |
| B3 the stamp is set on success only, to the monotonic clock | 5 | 5 | 0 | 0 |
| B4 inside the window the heartbeat is skipped; exactly at the limit still fresh | 4 | 3 | 1 | 0 |
| Total | 19 | 17 | 2 | 0 |

Totals counted from the table: 19 = 17+2+0; no invalid, no noapply. B4 mutants change the condition at both sites (agent.py:83 in `check` and :173 in `cross`, same text), so each B4 mutant is one change at two lines. B4 is pre-existing code that the new tests pin (the PR's own "exactly at the limit" test).

Survivors: none. Conditions: none blocking. Optional: one test through a real Liveness client with a failing transport. Confidence: HIGH on counts, MEDIUM on completeness. Token/cost: I do not know.
