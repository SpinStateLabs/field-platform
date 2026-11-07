# Review PR #858 (kill-switch: bound POST /heartbeat/{agent_id}: id rule, id length, unregistered row cap; B-RT4 F1) - ssl-ff-reviewer-10

**VERDICT: PASS WITH CONDITIONS** on head `e16546bed7377935ec3ba82c1318d46fd7ac14ab`. One condition (C1: the new cap makes a silent blind spot); one non-blocking mismatch (C2). The fix does stop the unbounded growth ssl-ff-reviewer-9 measured in R-RT-HARD-4 F1 (comms/inbox/coordinator/20261106-2134-ssl-ff-reviewer-9-rt-hard-4-operator-layer.md).

## Facts (HIGH, read from the head)
- 1 commit (e16546be); 3 files: services/kill-switch/src/kill_switch/api.py (+17/-4), store.py (+19/-3), tests/test_heartbeat_bounds_rt4.py (new, 100 lines). Nothing under .github/.
- Author and committer `Don Hagell <13129187+dhagell@users.noreply.github.com>`.
- The branch is level with main (merge base `41afda50`).
- The code: `POST /heartbeat/{agent_id}` refuses an id that is longer than `MAX_HEARTBEAT_ID_LEN` (128) or fails `fullmatch` against `[a-z0-9][a-z0-9._-]*` (the registry's own pattern) with a 422 and stores nothing; `HeartbeatStore.record(..., max_unregistered)` refuses a NEW id whose status is `unregistered` once 500 such rows exist (the route answers 429), always records an id already stored and any registered agent, and does the count and the write under one lock hold. No operator guard, on purpose: the PR body says a check-in is the agent's own self-report and an agent holds no operator key (the builder asks Don or the coordinator whether an agent-own-token variant is wanted).
- The agents' SDK treats any non-200 answer to a check-in as `HeartbeatUnreachable` ("liveness unknown, halting", `field_agent/liveness.py`), so a 422 or 429 makes the caller halt: fail closed.

## Verification (run by me, Windows 10, Python 3.14)
- tests/test_heartbeat_bounds_rt4.py: 5 passed (21 s). With the existing heartbeat, liveness and store tests (test_endpoint_and_liveness, test_heartbeat_store_concurrency, _lazy_init, _lock_coverage): 75 passed (6 min 26 s).
- Mutants (mine, 10 hand mutants on api.py and store.py, one at a time against the new file; files restored with `git checkout`, tree clean afterwards). Counted from the output: 10 RED, 0 survived: length check removed; pattern check removed; length bound `>=`; pattern with `match` instead of `fullmatch`; the cap never passed to the store; cap off by one; the cap also blocking an id already stored; the cap applying to registered agents; refusal answered 200 instead of 429; invalid id answered 400 instead of 422.

## Condition
**C1 (MEDIUM, confirmed by running): once 500 ghost ids have checked in, every later shadow agent is refused and invisible, with no sign of it anywhere.** Rows are never pruned or expired (the store has `record`, `get` and `all` only). Probe on the head (a registry stub, a temp sqlite file, 505 posts of `ghost-N`): the first 500 answer 200, the next 5 answer 429; a NEW `real-shadow-agent` then gets 429, its row does not exist, and `GET /liveness` does not list it; a registered agent still records (200); `/health` carries no counter of refused check-ins (the only refusal keys are the operator layer's `refused_count` and `dropped_refused_records`, which this is not). The check-in that surfaces a shadow agent is exactly what the route exists for ("so a shadow agent nobody registered still surfaces"); before this PR any number of rows were stored; now a perimeter-secret holder can fill the table with 500 ids and hide new shadow agents, and nobody is told the table is full. (The agent itself halts on the 429, so the shadow agent is stopped on its side, but the operator never learns it exists.)
Fix, any one: count and log every refused check-in and show it in `/health` (and add the saturation to `/liveness` output), so the blind spot is visible; or prune the oldest `unregistered` rows (least recently seen) instead of refusing a new one; or expire unregistered rows after a set age. Add a test for whichever is chosen.
Observed in the same probe: a ghost id that later registers frees its slot (the count is by `status = 'unregistered'`, and the upsert updates the status), so a new shadow agent gets 200 again.

## Non-blocking
**C2 (LOW-MEDIUM, confirmed): the length cap is not the registry's.** The comment and PR body say the id rule is the registry's own; the pattern is, but the registry sets no maximum length (`pattern` and `min_length=1` only). A REGISTERED agent whose id is longer than 128 characters (a 204-character `reg-...` id in my probe) gets 422 on every check-in and halts. Estate ids are short, so this is a mismatch to close, not a live fault: either give the registry the same `max_length` (so such an agent cannot be registered) or lift the heartbeat limit to match.

## Optional (LOW)
1. The two cap and length values are constants (128, 500), not tunable; the builder says so.
2. No operator guard on a route that writes: accepted by design in the PR body; Don or the coordinator may still want the agent-own-token variant.

## Not covered
CI and GX10 on this head; the whole kill-switch suite; a live estate; Linux.
