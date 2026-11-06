# ssl-ff-builder-9: B-RT4-killswitch-heartbeat-guard-and-bound -> draft PR 858

PR: https://github.com/SpinStateLabs/field-platform/pull/858 (draft). Head e16546bed7377935ec3ba82c1318d46fd7ac14ab, one commit, author AND committer Don Hagell noreply; remote head verified equal to local.
FIXED (F1): POST /heartbeat/{agent_id} now refuses an id outside the registry's agent-id rule or over 128 chars (422, nothing stored) and caps distinct unregistered rows at 500 (429 for a new one; stored and registered ids always record; count and write under one lock hold).
NO OPERATOR GUARD, by design: a check-in is the agent's own self-report and agents hold no operator key; guarding it would stop all check-ins. The card said "consistent with the other write routes"; this is the one departure and the PR body says why. Don/coordinator: say if you want the agent-own-token variant instead (reviewer left it open).
TESTS: tests/test_heartbeat_bounds_rt4.py, 5 tests. MUTANTS: 4 of 4 killed (no length check, no pattern, no cap, cap blocks known ids). 84 existing heartbeat/endpoint/liveness tests pass locally. CI not read yet.
Cap values are constants (128 / 500), not env-tunable.
