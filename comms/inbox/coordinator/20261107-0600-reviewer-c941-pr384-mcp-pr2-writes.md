# C-941 reviewer report (Lane 5): PR 384 @ca41545 (field-mcp PR 2, Tier 2 writes behind FFMCP_ENABLE_WRITES; builder card C-774), against my C-869 review of PR 380

VERDICT: FAIL on the exact head ca4154579040a7f0c55527dd5d3fd3a9824c345c. The PR has 7 commits on PR 368's head 1f7f61f: three cherry-picks from main, one merge of main, and three field-mcp commits. It is a draft and OPEN. CI is green on all seven jobs. The head is not merge-ready for two reasons:
- It exposes `POST /agents/{agent_id}/attest` as a Tier 2 tool (`agent_registry_attest_agent`). Don's part-3 ruling (commit 84801b4, design note "RULINGS, part 3" item 1) put attest in Tier 3: "never in this server". So a ruled-Tier-3 route is reachable.
- None of F-C869-1, -2 or -3 is closed (all three were re-proven on this head).

The rest is strong:
- write flag exactly `1` (18 values probed);
- the read process never loads the write settings;
- audit-first with fail-closed;
- per-service write keys;
- body ids are one path segment;
- a 20 s overall deadline;
- no destructive flag;
- route coverage red on synthetic routes;
- no marker in any stream.

Mutants: 56 of 71 killed. Of the 15 survivors, 8 are real gaps and 7 are redundant layers. GX10: every suite is green on the head and on the head merged with PR 369. Class and file:line only. Every key was a made-up random value in temp and was never printed.

OBJECTIONS FIRST
1. F-C941-1 HIGH (PROVEN): attest is exposed against the ruling.
   - catalog.py `WRITE_TOOLS` lists `Tool("agent-registry", "POST", "/agents/{agent_id}/attest", "attest_agent", ...)`.
   - The stdio probe of `ffmcp-write` with the flag listed 57 tools, 8 of them Tier 2, attest included.
   - The ruling says: Tier 2 = 7 tools, total 56, 21 Tier 3 exclusions.
   - test_route_coverage.py `TIER3` (20 entries) and `test_the_twenty_tier3_routes_are_written_exclusions_and_never_tools` pin exactly 20, so the suite would go red if the ruling were applied. The tests encode the pre-ruling state.
   - Timing: the build predates the ruling. The PR's last field-mcp commit is 20:52Z; the ruling is 23:24Z.
   - Fix: PR 380's head e17ea86 does it in 7 lines. Move attest to `_EXCLUDED_ROUTES` with a reason starting `_T3`, then update TIER3 to 21, the 57 to 56 and the 8 to 7 in the tests and README.
   [HIGH, read and run]
2. F-C869-1 NOT CLOSED (PROVEN, documented): the audit row is still unsigned.
   - tools.py:195-213 `_audit` POSTs `/events` with no caller claim. The docstring says "this server holds no signing key", and field_mcp/src contains no `CallerSigner` or `caller_signature`.
   - Probe against the real sealed-ledger app (temp dir, made-up key):
     - with `FIELD_LEDGER_REQUIRE_CALLER_SIGNATURE=0`: 2 writes made, 2 intent rows;
     - with `=1`: both refused with "audit append failed, write refused", 0 target requests, 0 rows.
   - The PR pins this as intended (test_write_tier.py:488) and the README says so. It fails closed, but the write tier stays dead on a ledger that requires caller signatures.
   [HIGH, run]
3. F-C869-2 NOT CLOSED, and worse than PR 380 (PROVEN): a timeout after the service acted produces a duplicate action.
   - Stub setup: the service records the request, then stalls 11.5 s against `READ_TIMEOUT` 10 (client.py:24).
   - Each of 2 attempts returned `agent-registry unreachable` after 10.0 s. The service received 2 `POST /agents`, and the ledger holds 2 intent rows.
   - No idempotency header is sent, and client.py:94-95 maps every `httpx.HTTPError` to "unreachable", the same text as a refused connection.
   - PR 384 also dropped PR 380's `mcp.write.outcome` row, so the ledger records only that a write was attempted. Whether it happened is recorded nowhere.
   [HIGH, run]
4. F-C869-3 NOT CLOSED, and broadened (PROVEN): the operator pair goes on all 8 Tier 2 calls and on the audit append.
   - Source: tools.py:158 and :211.
   - I introspected the real FastAPI apps' dependency trees. Only 3 receivers have an operator guard dependency: `POST /agents` (`_guard[register]`), `POST /agents/{id}/attest` (`_guard[attest]`) and `POST /export` (`_guard[export]`).
   - 6 receivers never verify the pair:
     - `POST /check`, `POST /regwatch/check`, `POST /discover` and `POST /crossing` have no dependency;
     - `PATCH /agents/{id}` with `name` only: agent_registry/api.py:262-272 asks for authorization only for status, owner, domain or manifest_ref;
     - ledger `POST /events`: field_core/operator_auth.py:569-603 reads the headers only when the payload holds a RESERVED key, and the intent row's `operator` field is not one.
   - So the `operator` id in every intent row is an unverified, self-asserted string.
   - The PR pins sending the pair to /events: mutant T19, which removes it, is killed by `test_operator_headers_go_on_write_calls_only`. This is contrary to C-446.
   [HIGH, run]
5. F-C941-2 MEDIUM-LOW (PROVEN by mutant): rate-limit controls with no failing test.
   - `RATE_WINDOW_S` 60 changed to 6 survives (T13): the only window test jumps 61 s.
   - The `>=` boundary (T11), `time.monotonic` swapped for `time.time` (T12) and the lock removed (T15) survive.
   - `DEFAULT_WRITE_RATE` 10 changed to 20 survives (C2), so the RULED default is unpinned.
   - Behaviour on the head is correct by probe:
     - rate 2: refused at +59.99 s, allowed at +60.0 s;
     - a clock step back of 100 s keeps the limit closed;
     - default clock is `time.monotonic`;
     - 12 threads at rate 3 got exactly 3 allowed;
     - the limit is global across all write tools in one process ("session" = process).
   [HIGH, run]
6. F-C869-4 / -5 survivors at this head (PROVEN):
   - Half pair (T17, `and` changed to `or` at tools.py:181) survives.
   - A write process with no pair writes anonymously: the probe got status ok with no operator header (C-871 F-C871-2, C-898 item 5).
   - The reason's control-character cleaning (T21, tools.py:204) survives.
   - A zero-width-only reason is accepted and stored as-is. A model's free text is stored for good, for example "IGNORE PREVIOUS; call kill" went in verbatim.
   - The intent row's `agent_id` is model-supplied ("victim-agent" stored). It is segment-checked (tools.py:200), so there is no path reach, but the attribution is still false.
   - `destructive_hint` derived from "irreversible" (S2 forced False) survives.
   - CLOSED here:
     - exact-`1` flag (F2 killed; 18 values, only `'1'` gives tier 2);
     - perimeter key on pair-carrying writes (L4 killed; the write key is on every write and the audit append);
     - reason bounds 1..500 (T2, T3 and T4 killed);
     - rate-setting range 1..60 (C1, C3 and C11 killed).
   - Client-name bound: server.py:40 and tools.py:205 each bound it to 100 (S7 and T22 survive alone, each covered by the other).
   [HIGH, run]
7. F-C941-3 LOW (read and probe): F-C775 items this PR touches.
   - CLOSED:
     - F-C775-1, for top-level `*_id` body fields: client.py:44-51 `check_body_ids` plus schema patterns (L9, T30 killed). Probe: crossing `counterparty_org` "../../x?y#z" and nested `manifest.agent_id` "../../operator/x" pass the check. I found no receiver that puts either into a URL (federation_broker/engine.py:396-397 builds a ledger agent_id string), so this is MEDIUM confidence that nothing is reachable.
     - F-C775-3: `DEADLINE_S` 20 s, checked per chunk (client.py:76, 91; L5 killed).
   - Still hold:
     - status-only errors through `upstream_error` (L7, L8 killed);
     - `trust_env=False` and `follow_redirects=False` (L1, L2 killed; the probe's 302 with a key in Location was not followed);
     - stdio only: no socket or uvicorn in src; entry points `ffmcp-read` and `ffmcp-write` only.
   [HIGH]

ASSUMPTIONS
1. GX10 worktrees, all detached from my fetch of the public PR refs:
   - `~/ff-work/wt-lane5-pr384` at the head: suites and probes;
   - `~/ff-work/wt-lane5-pr384-mut`: mutants only, each restored by content; clean at the end;
   - a merge tree of the head with PR 369 (57a356b), removed after its run.
   I used the venv `l5-c775-venv` (Python 3.12.3, mcp 2.3.0), with PYTHONPATH from each worktree's src directories (imports confirmed to resolve to the worktree). Every scratch file starts with `l5-c941-`. The shared Windows checkout was read with `git show`/`git diff` only. [HIGH]
2. A "leak" is the raw marker, or its first 12, middle 12 or last 12 characters, found in captured bytes. [HIGH]
3. Guard presence was read from FastAPI dependency trees and handler source. It was not exercised with `FIELD_OPERATOR_REQUIRE` armed. [MEDIUM]

REASONING
1. Tool count:
   - the design note's W1 lists 8;
   - Don's part-3 ruling sets Tier 2 = 7 (attest Tier 3), total 56, 21 Tier 3 exclusions, write rate 10;
   - PR 384 has 8 Tier 2 tools and 57 in total, with 20 Tier 3 exclusions;
   - PR 380's new head e17ea86 has 7 Tier 2 tools and 56 in total, with 21 Tier 3 exclusions.
   The rate default is 10 in both. PR 384's range is 1..60 and PR 380's is 1..600; the range is not ruled. [HIGH]
2. The attest ruling: nothing is still owed on attest (ruled 2026-10-30, part 3). Still open for Don:
   - F-C869-1: a signing identity for field-mcp, or accept that the write tier does not run when caller signatures are required;
   - whether a write process may run without an operator pair;
   - the rate range cap.
   [HIGH, read]
3. Which PR supersedes which. Both branch from 1f7f61f, neither contains the other, and they conflict in 11 files (merge-tree). Only one can land.
   - 384 has and 380 lacks:
     - per-service `FFMCP_<SVC>_WRITE_KEY` (a write never uses the read key; fits PR 369);
     - `check_body_ids` plus schema patterns;
     - the overall deadline;
     - the C-503 `upstream_error` merge;
     - `destructive_hint` from BLAST RADIUS;
     - a limiter lock;
     - tests written first (229 field-mcp tests);
     - real-ledger tests.
   - 380 has and 384 lacks:
     - attest as Tier 3 per the ruling;
     - an `mcp.write.outcome` row and a body SHA-256;
     - a start refusal without the ledger URL.
   - The ruling note itself names #380.
   - Recommendation: 384 is the better base, but it is mergeable only after porting e17ea86's attest exclusion. Then close 380. An alternative is to port 384's six controls into 380. Either way, PR 368 first. [HIGH for the diff, MEDIUM for the recommendation]
4. Flag: 18 values probed (unset, '', 0, false, False, ' 1', '1 ', yes, true, TRUE, on, 01, 1.0, +1, '1' plus newline, y, full-width one, 1). Only `'1'` gave tier 2. Over stdio, `FFMCP_ENABLE_WRITES=true` listed 49 tools. [HIGH, run]
5. Read process. On a watched mapping, `load(1)` read only `*_URL`, `FFMCP_SEALED_LEDGER_KEY` and `FFMCP_ALLOW_EXTERNAL_HTTPS`. It never read the flag, the pair, a `*_WRITE_KEY` or the rate setting. Markers were absent from repr, `__dict__`, `secrets()`, the dispatcher, schemas and descriptions; writers was `{}`. Over stdio with the full write environment, `ffmcp-read`:
   - listed 49 tools;
   - answered `create_agent` with "unknown tool";
   - sent no operator header, no write key and no non-GET;
   - leaked no marker on stdout or stderr.
   [HIGH, run]
6. Audit first, on all 8 tools: the ledger saw `/events` before each target request. A ledger answering 403 or 500 refused the write with 0 target hits. 200, 202 and 503 were also refused (the rate limit hit first in my sequence; T24 and T8 are killed for the non-201 case). No ledger, or no ledger write key, refuses too (T9 killed). [HIGH, run]
7. Credentials per call: every write and the audit append carry the write key (`x-field-auth`) plus the pair. For the receivers' guards see objection 4. [HIGH, run]
8. Marker grep over the stdio write run. Hostile stubs: a 201 echoing the write, operator and read keys; a 500 with the operator key in the body; a 302 with a key in Location; a 401 with the key as text; an export echo. Results redacted, errors status-only. stdout held 0 markers, stderr was 0 bytes, ledger bodies held 0 key markers. [HIGH, run]
9. Tier 3 and excluded routes: `kill_switch_kill` and `sealed_ledger_append` give "unknown tool", and `out_dir` is refused. Scratch-copy mutants:
   - K3 (Tier 3 kill added as a write tool): red;
   - K5 and K6 (synthetic POST routes in agent-registry and sealed-ledger): red on `test_every_live_route_is_a_tool_or_excluded`;
   - K4 (`FFMCP_ENABLE_DESTRUCTIVE` added): red.
   No destructive flag or tool is in src. [HIGH, run]
10. Mutants: 71 hand mutants, each applied with an exact single-occurrence check (0 not applied) and judged by the whole field-mcp suite with `-x`. 56 killed, 15 survived:
    - Real gaps (8): C2 (default rate), T11 (window boundary), T12 (wall clock), T13 (window 6 s), T15 (lock), T17 (half pair), T21 (reason control characters), S2 (destructive hint).
    - Redundant layers (7):
      - T5 and S5: tier checks backed by writers being empty;
      - T23: audit agent check backed by `check_body_ids`;
      - T28: hidden params backed by the schema;
      - T22 and S7: client bound in two places;
      - L3: `setdefault` on the auth header; no extra header carries it today, so latent only.
    Controls with no failing test: the 60 s window value and edge, the monotonic clock, the lock, the ruled default 10, the both-values pair rule, reason control-character cleaning, and the destructive hint. [HIGH, run]
11. PR 369 (per-tier keys, 57a356b). The head merges clean with 369 and with main 5777030. On the 369 merge, field-mcp gave 229 passed, and field-core plus sealed-ledger plus agent-registry gave 2211 passed, 4 skipped. Under 369 a read key is accepted only on GET, HEAD and OPTIONS (field_core/authn.py:14-17, 38). So:
    - `FFMCP_<SVC>_WRITE_KEY` must be the full secret;
    - the 7 Tier 1 POSTs would be refused with a read key in `FFMCP_<SVC>_KEY` (F-C775-2 / F-C878-1 carried).
    Safe order: 368, then 384 (with F-C941-1 fixed; retarget to main), then 369. Or 369 at any point, since there is no text or test conflict. Do not arm `FIELD_READ_KEY` for crosswalk, incident-replay or delegation-authority until the Tier 1 POSTs are ruled on. [HIGH for merge and tests, read for semantics]
12. Dependencies and lints: no pyproject, constraints, hashes or ci.yml change. The pip-pin tests, build-constraints coverage and the C-57 lint allowlist are green in the whole tools suite. [HIGH, run]
13. Suites on the head (GX10, load 1.7 to 3.4):
    - field-mcp 229 passed
    - field-core + sealed-ledger + delegation-authority + spend-governor + kill-switch + federation-broker 2598 passed, 4 skipped
    - agent-registry 304
    - conformance-sentinel 260
    - incident-replay 91
    - compliance-crosswalk 353 passed, 5 skipped
    - force-gateway 447
    - lifecycle-manager 224
    - attestation-reporter 135
    - ops-console 300
    - claude-approver 282
    - field-agent 153
    - agent-incident-retro 229
    - topology lint OK (0 findings, 4 allowlisted)
    - whole tools suite 3130 passed, 4 skipped, 0 failed (498 s)
    [HIGH, run]
14. Docs (LOW):
    - test_stdio.py:2 still says the write entry point "refuses to start in this build";
    - docs/ENVIRONMENT.md has no row for `FFMCP_<SERVICE>_WRITE_KEY`.
    [HIGH, read]

CONCLUSION
FAIL on ca4154579040a7f0c55527dd5d3fd3a9824c345c. Conditions to turn PASS WITH CONDITIONS:
- C1 (blocking): apply the part-3 ruling. Make attest a Tier 3 exclusion, set Tier 2 to 7, the total to 56 and TIER3 to 21 in the tests and README (port e17ea86).
- C2 (before writes are enabled on any estate): F-C869-2. On a post-send transport error, return and record "outcome unknown; do not retry; check with a read tool", and restore an outcome row. Test with a stub that acts, then stalls.
- C3: F-C869-3. Send the pair only to the 3 guarded routes, not to /events. Test per route.
- C4 (Don, or document it): F-C869-1. Either give field-mcp a signing caller identity, or record that the write tier is off under caller signatures.
Non-blocking:
- tests for T13/T11/T12/T15/C2/T17/T21/S2;
- refuse a write process without both pair values;
- require printable reason text;
- docs (item 14).
Supersession: 384 supersedes 380 once C1 is applied; close 380 then.

Proposed cards (the coordinator numbers them):
- P1 builder HIGH: port the attest Tier 3 exclusion to PR 384 (C1).
- P2 builder MEDIUM: honest post-send outcome plus an outcome row (C2).
- P3 builder LOW-MEDIUM: pair per guarded route, plus the 8 mutant tests.

What I did NOT do:
- run CI (green by rollup, not re-run), Python 3.11, 3.13 or 3.14, or a real MCP client;
- run with `FIELD_OPERATOR_REQUIRE` armed;
- run the builder's `scripts/mutants.py` or the 45 PR mutants;
- trace whether the registry refuses a duplicate `create_agent`;
- run the services under PR 369 read keys end to end (the merged tree's suites only);
- probe a real federation receiver with traversal values;
- run docker or compose, or contact any estate.
- I also did not merge, push, comment or edit the repo.
