# Review R-PR858-cd4a9e3: PR 858 (kill-switch: bound POST /heartbeat: id rule, length, unregistered cap; B-RT4 F1; policy enforcement point)
Head reviewed: cd4a9e37b5ccf1941528d61afd6dd7785055e6a1 (2 commits). Behind main; `git merge-tree` against main reports a CONFLICT in services/kill-switch/src/kill_switch/api.py (see C1).

## VERDICT: PASS WITH CONDITIONS (the bounds work as written; a rebase against main's S4-4, and a shadow agent that is neither recorded nor told to halt, reproduced below)

## Checks (HIGH, run by me)
1. Identity: both commits author AND committer Don Hagell 13129187+dhagell noreply; nothing under `.github/`; 3 files (api.py +33/-2, store.py +20/-2, a new 153-line test file).
2. Code read: `checkin` refuses (422, nothing stored) an id longer than 128 or not matching `[a-z0-9][a-z0-9._-]*` (the registry's own rule, models.py:22, 52); `HeartbeatStore.record(..., max_unregistered)` refuses a NEW id whose registry status is `unregistered` once 500 such rows exist (429); a stored id and any registered agent always record; the count and the write share one lock hold; a refusal increments `heartbeats_refused` (shown in `/health` and `/liveness`) and logs the first and every 100th.
3. Tests on head: test_heartbeat_bounds_rt4 8 passed (33 s). The PR body says 84 existing heartbeat tests pass; I did not re-run them.
4. Probe (ks858.py in my scratchpad; the PR's own fixture, cap set to 3): a valid shadow id answers 200 with `killed: true`; `MyBot` (upper case) answers 422 and no row is stored; the fourth distinct shadow id answers 429 `too many distinct unregistered agent ids have checked in` (no id echoed); a shadow id already stored still answers 200 at the cap; a registered `reg-*` agent answers 200 at the cap; `/liveness` shows the cap and the refused count; the table has no delete, purge or eviction method.
5. Mutants on api.py and store.py, 19 run: 17 killed, 2 survived (counted from table).
| # | Mutant | Result |
|---|---|---|
| K1 | no length check | killed |
| K2 | length `>=` (128 refused) | killed |
| K3 | no pattern check | killed |
| K4 | pattern uses `match` (prefix) | killed |
| K5 | cap not passed to the store | killed |
| K6 | known ids also blocked at the cap | killed |
| K7 | cap off by one (`n > max`) | killed |
| K8 | registered agents counted under the cap | killed |
| K9 | the count includes every row, not only unregistered | SURVIVED |
| K10 | refusal counter not incremented | killed |
| K11 | `/health` field removed | killed |
| K12 | `/liveness` refused field zeroed | killed |
| K13 | `/liveness` cap field zeroed | killed |
| K14 | refusal answers 503 | killed |
| K15 | malformed id answers 400 | killed |
| K16 | the store never refuses | killed |
| K17 | log line never written | killed |
| K18 | log line on every refusal | killed |
| K19 | refused id echoed in the 429 text | SURVIVED |

## Conditions
### C1 (MEDIUM): rebase; main already bounds this route (S4-4) and the head conflicts in api.py
Main (commit bb2f236d, "heartbeat POST bounds the id it records (S4-4)") has `MAX_HEARTBEAT_ID_LEN = 128` and a check `len(agent_id) > MAX_HEARTBEAT_ID_LEN or any(unicodedata.category(c) == "Cc" ...)` with the text "agent_id is too long or contains a control character". This PR defines the same constant and a stricter rule with another text. Rebase, keep one constant, decide which 422 text stands, and re-run main's S4-4 tests next to the new ones (they may assert main's text); identity re-check of the new head.

### C2 (MEDIUM, confirmed by running): a shadow agent past the cap, or with a malformed id, is not recorded and not told to halt
`checkin`'s own docstring says an unregistered check-in is recorded so that "a shadow agent nobody registered still surfaces and is still told to halt", and `_heartbeat_for` returns `killed: true` for it. After this PR: (a) a NEW unregistered id past the cap gets 429 with no `killed` field and no row (probe); (b) an unregistered id that fails the pattern (`MyBot`) gets 422, no row, and is not counted anywhere: the refused counter, `/health` and the log line cover only cap refusals (probe: `heartbeats_refused` stayed at the cap count after the 422). So an operator (or any perimeter-secret holder) who fills 500 slots, or a shadow agent that happens to use an upper-case id, is invisible to `/liveness` and never receives the halt answer; the PR says so for the cap ("new shadow agents are not being recorded") and makes it visible by a counter, but the 422 path has no trace at all.
Fix: count and log malformed-id refusals too (a second counter or the same one, never the id); and for the over-cap case consider answering 429 WITH the same body fields a halt answer carries, or state in the docstring that over the cap a shadow agent is only visible by the counter.

### C3 (LOW-MEDIUM, confirmed by running): a REGISTERED agent with an id over 128 characters can never check in
The registry's agent-id rule has a pattern and a minimum length but no maximum (models.py:22, 52); the kill-switch now refuses ids over 128. Probe: a registered agent with a 134-character id answers 422 on check-in and shows as `stale` in `/liveness` for good. Fix: cap the registry at 128 too (a registry change, a separate card) or document the limit; at least a test that pins the mismatch.

## Observations (LOW)
- No eviction: unregistered rows are never purged (no method on the store), so legitimate typo'd or retired ids accumulate toward 500 over time and then new shadow agents are invisible until an operator edits the database; the table clears a slot only when the id is later registered. A TTL for `unregistered` rows (for example 30 days) would remove that.
- K9: no test has registered rows beside unregistered ones when counting, so counting every row would pass; K19: no test pins that the 429 text never carries the id (it does not today, probe).
- The PR leaves two decisions to Don (cap values not env-tunable; whether a check-in needs the agent's own token); not defects.

## Not verified
The 84 existing heartbeat, endpoint and liveness tests; behaviour against a real registry; GX10 16/16.

## Conditions to reach PASS
C1 and C2 in a new commit (with tests); C3 decided (card or documented); identity re-check of the new head.
