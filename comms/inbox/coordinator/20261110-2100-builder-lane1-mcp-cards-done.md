# Builder Lane 1: MCP cards done or obsolete (queue lines still say OPEN)

For the coordinator to flip. Evidence only; I edited no card line.

| Card | State | Evidence |
|---|---|---|
| C-902 (close F-C869-1..3 on the MCP write tier) | DONE on PR 380 | commits db99294 (F-C869-3), b6af16d (F-C869-2), a8236ae (F-C869-1, signing through field-core `CallerSigner`), 56a7c2b; report 20261107-0900-builder-lane1-c902.md |
| C-929 (PR 380 conditions, reviewer C-869) | DONE except two named items | F-C869-1/-2/-3 by C-902; F-C869-4 (surviving-mutant pins), -7 (destructiveHint, stale docs), -8 (limiter lock) by the port commits 38ad224, a2d0e1f, 605e89b, a47e0af (report 20261107-1300-builder-lane1-c1014-port.md); F-C869-6 `attest` ruled Tier 3 by Don 2026-10-30 (commit e17ea86); F-C869-5 named out of scope (the model-supplied `agent_id` names the intended target; the reason text is cleaned). Reviewer delta needed on the current head |
| C-1014 (PR 384 conditions, reviewer C-941) | OBSOLETE for PR 384, ported to PR 380 | PR 384 is closed (not merged, closed 2026-10-31T01:07Z on GitHub). The 9-commit patch (local head d98adddd, `git am` reproduces tree 31ca5f65) is on comms (20261107-1000-builder-lane1-c1014.{md,patch}) and was NOT pushed to Lane 16's branch (Don, option 1: leave PR 384 closed, port the leftovers to 380) |
| C-1033 (Lane 16: apply the Lane 1 patch to PR 384) | OBSOLETE in my view (coordinator decides) | same reason: PR 384 is closed; nothing to apply it to |

Current state of the live MCP Tier 2 PR (SpinStateLabs/field-platform#380): head b8af78f3a2476a632d16e6765140356e53e2b642, open, ready for review, mergeable, GitHub CI 7 of 7 green on that head (checked 2026-10-31 and again later); field-mcp suite 198 passed locally (3.13). Don ruled 2026-10-31 that the write process refuses to start without the whole operator pair (commit b8af78f; env doc rows, mutants OP1-OP3). PR 368 (Tier 1) is open, head 1f7f61f, CI 7 of 7 green; merge it first, then 380 shrinks to Tier 2 only.

Not done: the GX10 full run on either PR (the cloud session cannot reach the GX10); `runbatch.sh` is not in the repo, so the suite is not listed there; `hosts.py` in field-mcp still uses its local internal-host predicate until PR 356 (C-489) is on main.

Cards I looked at and did NOT take (each is the PR author's to close; no builder note exists for C-1008, C-1013, C-1017): C-1008 (PR 343), C-1013 (PR 382), C-1017 (PR 342), C-1009, C-1012, C-1026.
