# C-869 reviewer report (Lane 5): PR 380 @7551327 (field-mcp PR 2, Tier 2 write tools in a separate write process; builder card C-774)

VERDICT: PASS WITH CONDITIONS on the exact head 75513276a225fe511a6d893eed35249ee5fc75ff (2 commits, 9353565 and 7551327, on PR 368's head 1f7f61f, still OPEN; 14 files). The write controls the card names hold in code and under probe: writes are off unless `FFMCP_ENABLE_WRITES` is exactly `1`; the read process never reads the write flag, the operator pair or the rate setting; the ledger intent row is written before the call, and any ledger failure refuses the write; the limit is per process; no `FFMCP_ENABLE_DESTRUCTIVE` exists; no Tier 3 or excluded route is reachable; no made-up marker appeared in any stream I captured. Mutants: 51 of 61 hand mutants killed (M7, M9 and M18 killed). GX10: every suite green on the head (below). CI on GitHub: the four `tests` jobs, compose-smoke and fly-image-smoke had no conclusion (not run) at review time; only compose-upgrade-smoke had passed. Conditions: F-C869-1 to -3 before writes are enabled on any estate, plus Don's ruling on `attest`. Class and file:line only. Every marker was a made-up random value in temp and was never printed.

OBJECTIONS FIRST
1. F-C869-1 MEDIUM (PROVEN): on a ledger that requires caller signatures, the write process cannot write at all. The intent row is a plain `POST /events` with no caller fields (audit.py:49-50). `mcp.write.intent` is a start-type event (sealed_ledger/store.py:198-205 lists only `delegation.revoke`, `lifecycle.decommissioned` and `kill.*` as stop types). With `FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=1` the ledger answers 403 to a start-type event that carries no caller signature (sealed_ledger/api.py:356-370). Probe: the real sealed-ledger app with the caller policy armed, and a stub target. `create_agent` and `check` both returned "audit unavailable; no write made", with 0 target requests and 0 ledger rows. Unarmed, both calls succeed and 4 rows are stored. This fails closed, which is the safe direction. But the CI comment calls this setting "the GB10 ledger configuration" (ci.yml, tools step). On that estate the feature is dead, and the PR body lists the question as "unverified". Fix: append through field-core's signed-caller path (`CallerSigner`, `signed_append_body`) using a field-mcp caller key in the ledger keyring. Otherwise, say in the README that the write process does not work with caller signatures required. [HIGH, run]
2. F-C869-2 MEDIUM (PROVEN): a write that times out after the service acted is reported as failed, and a retry acts twice. The stub held `POST /agents` for 11 s against `READ_TIMEOUT` 10 (client.py:21). Both attempts returned `agent-registry unreachable`, yet the service received 2 `POST /agents`. The ledger holds 2 intent rows and 2 outcome rows, both reading "agent-registry unreachable". So C-692's "one event per act" holds for intents, but each outcome row states a failure for a write that took effect. No idempotency key reaches the service (tools.py `_write`). The registry's own duplicate check may protect `create_agent` (not traced). `check` (a verdict plus spend metering), `crossing` (a verdict), `regwatch_check`, `export` and `discover` are not idempotent. Fix: on a transport error after the request was sent, return and record "outcome unknown; do not retry; check with a read tool", rather than the same text as a refused connection. [HIGH, run]
3. F-C869-3 MEDIUM-LOW (PROVEN): the operator pair goes on every Tier 2 call (tools.py `_write`, `if self.cfg.operator and self.cfg.operator_key`), including 5 routes that check no operator: sentinel `POST /check` (conformance_sentinel/api.py:93), crosswalk `POST /regwatch/check` (compliance_crosswalk/api.py:153), registry `POST /discover`, broker `POST /crossing` (federation_broker/api.py:94), and `PATCH /agents/{id}` with `name` only (agent_registry/api.py:262-272 guards only status, owner, domain and manifest_ref). Only `POST /agents` (`guard_register`, agent_registry/api.py:218-221) and `POST /export` (`guard_export`, sealed_ledger/api.py:286, 441-443) are guarded. The stdio probe saw `x-field-operator-key` on `/check` and `/discover`. This breaks the rule set for the console in C-446 (the pair only on guarded writes): the key travels to services that never verify it. No test pins per-route sending. Fix: a per-tool `operator=True` set to the two guarded routes, plus a test. [HIGH, run and read]
4. F-C869-4 MEDIUM-LOW (PROVEN by mutant): several controls hold on the head but have no failing test:
   - M7b: accepting `true`/`yes` and stripping whitespace on the write flag survives. Only "unset" is pinned (test_config.py:72-76), not the exact-`1` rule.
   - L7: the perimeter key `x-field-auth` dropped from writes that carry the operator pair survives. No test asserts that a write carries the perimeter key.
   - T6: the pair sent when only one of the two values is configured survives.
   - T9 and T10: the reason length bounds (300 and 1) survive. This matches C-871 F-C871-1.
   - A6: the client-name bound of 100 survives.
   - R2 (`>=` against `>` at 60 s) and R5 (`time.time` for `time.monotonic`) survive. The window does not survive a wall-clock jump on the monotonic choice, and no test covers it.
   [HIGH, run]
5. F-C869-5 LOW-MEDIUM (PROVEN): model-supplied text and ids go into the irreversible ledger:
   - The intent row's `agent_id` comes from the arguments or from `body.agent_id` (audit.py `intent`). For `check`, that field is unpatterned (`minLength 1` only, snapshot). Probe: `check` with `agent_id` "victim-agent" stored `mcp.write.intent` attributed to "victim-agent". The crosswalk counts by event type (compliance_crosswalk/engine.py:154-171), so no count changes. Incident replay timelines would show the row.
   - `reason` (model text, up to 300 characters; control characters accepted per C-871) is stored for good. Tier 1 ledger read tools then return it to later sessions. This is a stored channel from one session's model into the next one's context. The `untrusted_data` envelope is the only mitigation.
   - The same unpatterned body ids reach the sentinel's f-string lookups (conformance_sentinel/engine.py:82-84, 108; field_core/clients.py:362). httpx turns `x/../../operator/rotation-state` into the request path `/operator/rotation-state` (probed). Encoded `%2F` stays encoded, and `?` cuts the path into a query.
   - This is the F-C775-1 class, carried as F-C871-4. The sentinel's lookups are GET only, so no write route is reachable this way. Its `POST /spend` sends the id in JSON, not in the path.
   [HIGH for the reach, MEDIUM for impact]
6. F-C869-6 LOW-MEDIUM: the eighth Tier 2 tool, `POST /agents/{agent_id}/attest`, is missing on purpose and documented in four places:
   - the PR body ("held back; needs Don's ruling");
   - the README ("Held back from Tier 2: registry `attest`");
   - catalog.py `_EXCLUDED_ROUTES`, with the reason "records a HUMAN re-attestation (attested_by names a human, agent_registry/api.py:92-102) ... Tier 3 candidate, awaiting Don's ruling";
   - test_route_coverage.py `test_the_counts_match_the_rulings`, which pins it as excluded (my mutant K3 is red).

   The reasoning is sound, since `attested_by` names a human. But it departs from a RULED item: D3 set Tier 2 at 8. So it needs Don's ruling, not only a note. Two narrowings are in the same category: `rename_agent` offers `name` only, and `export` cannot choose `out_dir`. Both are stricter than the ruling and pinned (K1, K2, T11-T15 killed). [HIGH, read and run]
7. F-C869-7 LOW (carried): `destructive_hint=False` on every Tier 2 tool (server.py:41; C-871 F-C871-3). docs/ENVIRONMENT.md:47 still says "No Tier 2 tools exist in this build" (C-878 F-C878-3). The test_stdio.py module docstring still says the write entry point "refuses to start in this build". A write process with no operator pair writes anonymously (C-871 F-C871-2): the README now says so under "What it does NOT claim", but the process does not refuse. [HIGH, read]
8. F-C869-8 LOW (read; not reproduced): the SDK runs tool calls concurrently (the stdio probe saw the `/check` request arrive before the earlier `/agents` call). `RateLimiter.allow` holds no lock (audit.py:30-38). Eight threads with limit 2, including a clock forced to yield, gave exactly 2 allowed, so the GIL window was not hit. The limiter is global across all tools for one process (the "session" is the process), uses a 60 s sliding window and a default of 10, and refuses before any request (pinned). A refused audit still uses up a slot (C-871). [MEDIUM]

ASSUMPTIONS
1. Own GX10 worktrees:
   - `~/ff-work/wt-lane5-pr380` at the head: suites and probes.
   - `~/ff-work/wt-lane5-pr380-mut`: mutants only. Each was restored by content, and the tree was clean at the end.
   - `~/ff-work/wt-lane5-pr380-mrg`: the head merged with PR 369 at 57a356b.
   I reused the CI-order venv `l5-c775-venv` (Python 3.12.3, mcp 2.3.0, pinned closure), with PYTHONPATH from each worktree's `src` directories. A check confirmed that imports resolve to the worktree. Python 3.11, 3.13 and 3.14 were not run. Every file I created starts with `l5-c869-`. [HIGH]
2. A "leak" means the raw marker, a 12-character prefix or an inner slice found in captured bytes. [HIGH]
3. The guard mapping is read from the route handlers. I did not exercise it with `FIELD_OPERATOR_REQUIRE` armed. [MEDIUM]

REASONING
1. Tool count. The note's W1 has 8 entries (design note table row "W1 write"): sentinel `/check`; crosswalk `/regwatch/check`; registry `POST /agents`, `PATCH /agents/{id}`, `/agents/{id}/attest`, `/discover`; federation `/crossing`; ledger `/export`. The code has 7 (catalog.py `TOOLS_TIER2`), and the stdio probe of `ffmcp-write` lists 56 = 49 + 7. The missing one is `attest` (finding 6). [HIGH]
2. Write flag (config.py `load`, `!= "1"`). I probed 13 values. Unset, `''`, `'0'`, `'false'`, `'False'`, `' 1'`, `'1 '`, `'yes'`, `'true'`, `'TRUE'`, `'on'` and `'01'` were all refused. Only `'1'` enables. This matches the design's "needs `FFMCP_ENABLE_WRITES=1`". The write process also refuses to start without `FFMCP_SEALED_LEDGER_URL`, and refuses a rate outside 1 to 600 (mutants C1, C2, C3 and C5 killed). M7 (default on) was killed by test_config.py. [HIGH, run]
3. Read process. `load(1, env)` on a watched mapping read only the URL and KEY variables and `FFMCP_ALLOW_EXTERNAL_HTTPS`. It never read `FFMCP_ENABLE_WRITES`, `FFMCP_OPERATOR`, `FFMCP_OPERATOR_KEY` or `FFMCP_WRITE_RATE_PER_MIN`.
   - Markers in those four variables appeared in neither `repr(Config)`, `cfg.__dict__`, `secrets()`, the dispatcher's `__dict__` nor any schema. The dispatcher held `audit=None` and listed no Tier 2 tool.
   - Over stdio, with the full write environment including the markers, `ffmcp-read` listed 49 tools and answered `create_agent` with "unknown tool". Upstream saw no operator header and no non-GET request. stdout and stderr held no operator, flag or rate marker.
   - Residual: if one client config gives both processes the same environment block, the read process's OS environment (`/proc/<pid>/environ`) holds the operator key even though the code never loads it. The README launch example is per-process.
   - C4 (read loads the pair) and M18/M18b (read lists Tier 2) were killed. [HIGH, run]
4. Audit first. The order is limiter, then intent append, then call, then outcome (tools.py `_write`, audit.py).
   - A ledger answering 403, 500 or 503, an unreachable ledger, `ledger=None`, `audit=None`, and a real ledger refusing on the caller signature all gave "audit unavailable; no write made" with 0 target requests (PR tests plus my probe).
   - The intent payload holds tool, service, method, path, scalar targets, the body's SHA-256, reason, operator id, session id and client name. It never holds the body or a key (the ledger request bodies were grepped: only the operator id, by design).
   - Mutants A1 (intent append swallowed), A2, A3, T1, T2 (call before intent), T3, T4 and A7 were killed. [HIGH, run]
5. Rate limit: finding 8. M9 (`if False:`) was killed by test_tier2.py `test_rate_limit_is_per_session_and_refuses_before_any_request`. R1, R3 and R4 were killed; R2 and R5 survived. [HIGH, run]
6. No Tier 3. Nothing in the package defines a destructive environment variable or flag: `FFMCP_ENABLE_DESTRUCTIVE` appears only as the subject of a test (test_dispatch.py:78), in the builder's mutant script and in the README Tier 3 row. K4 (flag added) was killed. Exposure was checked three ways:
   - K5 (Tier 3 `kill` added to the write catalog) was red.
   - K5b swapped `export` for `sealed-ledger POST /rotate`, removed the exclusion and regenerated the snapshot. It was red on 5 tests, including the literal banned-path list (`test_nothing_that_changes_status_or_authority_is_a_tier2_tool`), which covers every one of the 20 Tier 3 paths. This closes my F-C775-6 for Tier 2.
   - K6 (a synthetic `POST /l5c869-synth` route in agent-registry) was red on `test_every_live_route_is_a_tool_or_excluded`.
   [HIGH, run]
7. Per tool: route, method and credential:
   - check POST /check (pair, unguarded)
   - regwatch_check POST /regwatch/check (pair, unguarded; no body)
   - create_agent POST /agents (pair, guarded)
   - rename_agent PATCH /agents/{agent_id} (pair, unguarded for name; path id SEGMENT-checked, `../kill` refused)
   - discover POST /discover (pair, unguarded)
   - crossing POST /crossing (pair, unguarded)
   - export POST /export (pair, guarded; `out_dir` absent from the schema and refused as an argument)

   Every call also carries the shared perimeter key from `FFMCP_<SVC>_KEY`. The audit append carries that key only, with no pair (pinned). [HIGH]
8. Response handling and markers. I ran the stdio probe with a service-key marker and an operator-key marker against hostile stubs: a 201 that echoes both keys, a 500 with the key in the body, a 302 to a URL holding the key, and a 401 with the key in plain text.
   - Results were redacted, and every error was status-only.
   - The redirect was not followed: no request reached the Location.
   - stdout held 0 markers, stderr was 0 bytes, and the ledger request bodies held 0 key markers.
   - `trust_env=False` and `follow_redirects=False` are on the client (client.py:34-36). Forcing `follow_redirects=True` per call (L2) was killed, as were L3, L4 and L5.
   - No listening socket: the code imports only `mcp.server.stdio` (server.py), unchanged from C-775. [HIGH, run]
9. Prompt-injection surface. Descriptions are fixed text from the catalog plus method, path and service, and the Tier 2 surface is pinned by hash (T19 killed). They contain no imperative to the model. `discover` says "never pass real secrets", advice to the caller. Results keep the `untrusted_data` envelope. Stored reason text: finding 5. [HIGH]
10. Dependencies and lints. The PR changes no pyproject, constraints, hashes file or ci.yml, so the pip pin tests and the build-constraints coverage are unaffected. The C-57 lint stays green with no new allowlist line, since the only constructor is unchanged. Both checks ran in the whole tools suite. [HIGH]
11. PR 369. `git merge-tree` of 7551327 with 57a356b is clean (docs/ENVIRONMENT.md auto-merges). PR 380 already contains PR 368. On the merged tree: field-mcp 123 passed; field-core plus sealed-ledger 1907 passed, 4 skipped. The semantic conflict stays: F-C775-2 / F-C878-1, plus the write process needing the full key for every Tier 2 service and the ledger. Safe order: 368, then 380 (retarget to main), then 369. Or 369 first: no text or test conflict either way. Do not arm read keys for any service field-mcp uses until the 7 Tier 1 POSTs are ruled on. [HIGH for merge and tests, read for semantics]
12. Mutants: 61 hand mutants, each applied with an exact single-occurrence check (0 not applied). Each was judged by the whole field-mcp suite with `-x`, except K5b (full suite, no `-x`).
    - 51 killed.
    - 10 survived: M7b, L7, T6, T9, T10, A6, R2 and R5 are real gaps (finding 4). A4 (body excluded by name anyway) and T16 (out_dir dropped from params, already refused by the schema) are equivalent.
    - Controls with no failing test: the exact-`1` flag spelling; the perimeter key on writes; the pair needing both values; the reason bounds; the client-name bound; the window boundary and the monotonic clock; sending the pair per route (finding 3). [HIGH, run]
13. Suites on the head (GX10, load 2.8 to 5.4):
    - field-mcp 123 passed
    - field-core + sealed-ledger + delegation-authority + spend-governor + kill-switch + federation-broker 2585 passed, 4 skipped
    - agent-registry 304
    - conformance-sentinel 256
    - incident-replay 91
    - compliance-crosswalk 353 passed, 5 skipped
    - force-gateway 443
    - lifecycle-manager 224
    - attestation-reporter 135
    - ops-console 300
    - claude-approver 282
    - field-agent 151
    - agent-incident-retro 229
    - topology lint OK (0 findings, 4 allowlisted)
    - whole tools suite 3129 passed, 4 skipped, 0 failed (499 s)

    [HIGH, run]

CONCLUSION
PASS WITH CONDITIONS on 75513276a225fe511a6d893eed35249ee5fc75ff. The tier split, the off-by-default flag, audit-first with fail-closed, the rate limit and the absence of Tier 3 are real, and each has a test that dies without it.
Conditions before writes are enabled on any estate:
- C1: F-C869-1. Sign the audit append, or document that the write process cannot run with caller signatures required.
- C2: F-C869-2. "Outcome unknown, do not retry" on a post-send transport error, with a test.
- C3: F-C869-3. The pair on the two guarded routes only, with a test.
- C4: Don rules on `attest` (Tier 2 as ruled, or Tier 3).

Follow-ups (non-blocking):
- F-C869-4: tests for M7b, L7, T6, T9/T10, A6 and R5.
- F-C869-5: pattern-bind body ids on `check` and `crossing`, and restrict `reason` to printable text.
- F-C869-7: docs and annotations.

Proposed cards (the coordinator numbers them):
- P1 builder MEDIUM, field-mcp audit.py: signed caller append, with a test against the real ledger with `require_caller_signature`.
- P2 builder MEDIUM, field-mcp tools.py/client.py: distinguish a refused connection from a post-send timeout on Tier 2; mutant: the two collapsed.
- P3 builder LOW-MEDIUM: an `operator` flag per Tier 2 tool, plus the mutant tests listed in finding 4.

What I did NOT do:
- Run CI (queued), Python 3.11, 3.13 or 3.14, or a real MCP client.
- Run with `FIELD_OPERATOR_REQUIRE` armed.
- Run the builder's own `scripts/mutants.py` (read only).
- Trace whether the registry refuses a duplicate `create_agent`.
- Run the sentinel end to end with a traversal id (the httpx path rewrite was probed alone).
- Run the services under PR 369 read keys (the merged tree's suites only).
- Run docker or compose, or contact any estate.
