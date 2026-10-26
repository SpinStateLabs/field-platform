# claude-approver

The FIELD approver for **Claude Managed Agents** (beta `managed-agents-2026-04-01`): every
tool call a Managed Agents session pauses on (`evaluated_permission: "ask"`, i.e.
`always_ask`, or `auto` with no determination) is answered with the
**conformance-sentinel's verdict**. FIELD letter **E** (Enforcement). Pattern C of
`FORCE-FIELD/tasks/claude-platform-deploy-target-evaluation-2026-10-26.md` section 4.3; pilot
slice S2. Version 0.1.0, **flags OFF**: compose profile `approver`, never started by a plain `up`.

**A client, not an authority** (`docs/INTEGRATION.md` section 1). Every verdict is the
sentinel's and is ledgered by the sentinel; this service holds no policy, writes nothing to the
ledger itself, and on any doubt **denies**.

## What one poll does (`tick()`, every `CLAUDE_APPROVER_POLL_SECONDS`, default 2 s)

For every Console agent in the agent map:

1. `beta.sessions.list(agent_id=<console id>)` (auto-paginated; archived sessions are excluded
   by the API default). A returned session whose `agent.id` is not that id is skipped; so is one
   on another environment when `CLAUDE_APPROVER_ENVIRONMENT_ID` is set.
2. For an `idle` session: the events after the session's cursor (`events.list(created_at_gte=
   <newest processed_at seen>, order="asc")`, deduplicated by event id; the first read takes
   everything). The SDK's Session object has no `stop_reason`, so it is read off the latest
   `session.status_idle` event. When it is `requires_action`, each `agent.tool_use` /
   `agent.mcp_tool_use` with `evaluated_permission == "ask"`, no `user.tool_confirmation`
   naming it, and (when the idle carries `stop_reason.event_ids`) named in that list is checked:
   `POST <sentinel>/check {agent_id, action, token_id, irreversible: false, context: {source:
   "claude-approver", console_session_id, console_agent_id, tool_name, event_id, event_type,
   mcp_server_name?, session_thread_id?}}` (10 s timeout), then answered with
   `user.tool_confirmation {tool_use_id: <event id>, result}`. An ask read before that idle and
   not in its `event_ids` (a turn ended by `user.interrupt`) is never answered, now or later
   (`asks_superseded`); without `event_ids` every open ask is answered. All of one session's
   confirmations go in one `events.send`. A 4xx on a single-event send is **terminal** for that
   event: it is never re-checked or re-sent (`confirm_rejected`); a batch refused 4xx is split so
   one stale confirmation cannot strand the rest; a 5xx, transport error, 408 or 429 is retried
   next tick (a fresh sentinel check) and never split into a burst.
   After each delivered confirmation: `POST <kill-switch>/heartbeat/<field agent id>` (best
   effort, counted, never raised).
3. Usage, for every listed session of a usable entry (any status): the session's cumulative
   `usage` minus the last snapshot POSTED for it (`$FIELD_DATA_DIR/claude-approver/
   usage-cursor.json`, atomic replace) goes to `POST <governor>/usage {agent_id, model,
   input_tokens, output_tokens, cache_read_tokens, note: "console session <sid>"}`. `model` is
   the session's own agent snapshot `agent.model.id`, else `agents.retrieve(...).model.id`
   (cached per tick), else `unknown` (the governor then ledgers `usage.unpriced`). Only positive
   deltas; the cursor moves only on a 201 (a 404 "no cap" or any failure retries next tick).

| Sentinel answer | Confirmation | `deny_message` |
|---|---|---|
| 200, `decision == "ALLOW"` exactly | `allow` | none |
| 200, `BLOCK` | `deny` | `<clause_id>: <reasons joined by "; ">` |
| 200, `ESCALATE` | `deny` (a human holds the item) | `escalated: a human holds this item; <clause_id>: <reasons>` |
| exception, timeout, non-200, non-JSON, non-object, any other decision | `deny` | `claude-approver: <reason>` |
| map entry unusable (no `field_agent_id`, bad types, bad estate URL) | `deny`, nothing else happens | `claude-approver: <problem>` |
| estate `secret_file` configured but unreadable/blank | `deny` | `claude-approver: estate secret unreadable` |
| `CLAUDE_APPROVER_TOOL_MAP` invalid | `deny` | `claude-approver: CLAUDE_APPROVER_TOOL_MAP is ...` |

A session with an unanswered `agent.custom_tool_use` is **left untouched** (v0 does not execute
custom tools) and counted `custom_tool_pending`.

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/health` | GET | Open. `{ok, service: "claude-approver", version, build_sha, key_file_present, polling}`. Never the key or any part of it |
| `/stats` | GET | Behind `x-field-auth` when `FIELD_SHARED_SECRET` is set. Counters `allowed`, `denied` by class (`sentinel_block`, `sentinel_escalate`, `sentinel_error`, `unmapped`, `config_error`), `heartbeats`, `heartbeat_failures`, `usage_posts`, `usage_failures`, `ticks`, `last_tick_at`, `custom_tool_pending`, `confirm_rejected`, `asks_superseded`, `send_failures`, `list_failures`, map/cursor errors; the last 500 decisions `{at, console_session_id, event_id, tool_name, action, decision, sentinel_decision, reason_class, clause_id, shadowed, ms_sentinel, ms_total, sent, rejected?}`; p50/p95 of `ms_sentinel` and `ms_total` (nearest rank). This is where the S2 latency numbers are read |
| `/halt/{field_agent_id}` | POST | The kill-switch endpoint for the allowlist. Needs `x-field-kill-origin: kill-switch` (403 otherwise, nothing changes); unmapped id 404; no API key 503. Sends `user.interrupt` to every non-terminal session of the agent's Console id(s) first, then polls `sessions.retrieve` until the status is `idle` or `terminated` (up to `CLAUDE_APPROVER_HALT_WAIT_SECONDS`, default 20) and archives; a session still `running` or `rescheduling` (a live session being moved) is reported `archived: false`, never force-archived. 200 `{agent_id, reason, sessions: [{id, interrupted, archived, final_status, error?}]}`; `reason` is `x-field-kill-reason` percent-decoded, first 512 characters, echoed back and never logged. Exempt from the perimeter (see Declared) |

`approver serve --host 127.0.0.1 --port 8014` (poller in a daemon thread + uvicorn),
`approver version`.

## Configuration

| Env | Meaning |
|---|---|
| `CLAUDE_APPROVER_API_KEY_FILE` | File holding the org API key (default `/run/claude-approver/api-key`; compose sets that). Re-read every poll, trimmed; a changed key rebuilds the client. Absent/unreadable/blank: no polling, `/health.key_file_present=false`, `/halt` 503 |
| `CLAUDE_APPROVER_AGENT_MAP` | Inline JSON, or a path when the value names an existing file. `CLAUDE_APPROVER_AGENT_MAP_FILE` (a path) wins when set. Re-read every poll |
| `CLAUDE_APPROVER_TOOL_MAP` | JSON tool name -> FIELD action string (global layer) |
| `CLAUDE_APPROVER_POLL_SECONDS` | default 2.0, floor 0.5 (0 would spin against the rate limit) |
| `CLAUDE_APPROVER_ENVIRONMENT_ID` | optional: only sessions on this environment are approved (a `/halt` covers every session of the agent) |
| `CLAUDE_APPROVER_HALT_WAIT_SECONDS` | default 20 |
| `FIELD_SENTINEL_URL`, `FIELD_KILLSWITCH_URL`, `FIELD_GOVERNOR_URL`, `FIELD_SHARED_SECRET`, `FIELD_DATA_DIR` | as every service; the default route for agents without an estate block |

Agent map (keys starting with `_` are ignored; the shape of
`FORCE-FIELD/tasks/claude-platform-examples/ssl-timekeeping-agent/approver-map.json`):

```json
{
  "_comment": "Console agent id -> FIELD identity",
  "agent_011...": {
    "field_agent_id": "ssl-timekeeping-agent",
    "token_id": "<delegation token id>",
    "actions": {"read": "draft daily timesheet", "write": "draft daily timesheet"},
    "custom_tools": {"enter_time_in_portal": "enter time in client portal"},
    "estate_base_url": "https://force-field-sandbox.fly.dev",
    "secret_file": "/run/claude-approver/fly-secret"
  }
}
```

Action string for a tool call: per-agent `actions[tool]` > `CLAUDE_APPROVER_TOOL_MAP[tool]` >
built-in default (`bash`, `write`, `edit` -> `run commands in sandbox`; anything else, MCP tools
included, -> its own name, which the sentinel BLOCKs `D.scope` unless it is in scope).
`estate_base_url` (optional) routes that agent's sentinel, kill-switch and governor calls to
`<base>/sentinel`, `<base>/killswitch`, `<base>/governor` with `x-field-auth` read from
`secret_file` on every request (each sentinel, heartbeat and usage call; absent `secret_file` =
no perimeter header for that estate). The URL must not carry credentials (`user:pass@`): such an
entry is unusable and its calls are denied, because httpx logs request URLs. Without
it the env URLs and `field_core.authn.auth_headers()` apply (the GB10 stack). Structural garbage
(invalid JSON, not an object) empties the whole map: nothing is touched, `/stats` says why.

## Running it on the GB10 (pilot S2; nothing armed by this change)

1. Don places the key (never an agent): `install -d -m 0700 /home/spinner/.field-local/claude-approver`,
   then the key in `api-key` there, `0600`. The agent map goes in the same directory as
   `agent-map.json` (it holds a delegation token id: keep it there, not in `.env`).
2. In `integration/demo/.env`: `CLAUDE_APPROVER_SECRETS_DIR=/home/spinner/.field-local/claude-approver`
   and `CLAUDE_APPROVER_AGENT_MAP=/run/claude-approver/agent-map.json`. The default
   `./approver-secrets/` is a committed, git-ignored placeholder holding no key.
3. Build and start only this service, **with `--no-deps`**:
   `FIELD_BUILD_SHA=$(git rev-parse HEAD) docker compose -p field-platform -f integration/demo/docker-compose.yml -f integration/demo/docker-compose.gb10.yml --profile approver up -d --no-deps --build approver`
   Never drop `--no-deps`: `approver`'s `depends_on` (sentinel, killswitch, governor, and
   manifests-admin on the GB10) is start ordering for a fresh project only, and without the flag
   `up --build approver` would also build and recreate those ENFORCE services at the checkout's
   SHA, outside the gated runbook sequence. Add `--dry-run` first to see what it would touch.
4. Check: `/health` (`key_file_present: true`, `polling: true`), then `/stats` with `x-field-auth`
   from inside the compose network (no published port).
5. For a kill to halt sessions, the agent's manifest declares
   `enforcement.kill_switch.endpoint: http://approver:8014/halt/<field agent id>` and
   `FIELD_KILL_ENDPOINT_ALLOWLIST` gains `approver` (an arming step, not part of this change).

Rollback: `docker compose -p field-platform ... --profile approver stop approver` then
`... --profile approver rm -f approver` (both act on the named service only; never a bare
`down`, which would stop the whole estate). Nothing else references the service.

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| An `allow` only on an exact sentinel `ALLOW` from a 200 | **Enforced in code** | one producer of `allow` (`core.Approver._check`); tests for 503, 201, non-JSON, non-object, `allow`, `" ALLOW"`, `true`, missing and unknown decisions; mutant: with the ALLOW branch deleted every test that expects an allow fails (17 of 17) |
| Every failure path denies | **Enforced in code** | exception, timeout, non-200, non-JSON, unknown decision, unusable entry, unreadable estate secret, invalid tool map: each a test |
| An unusable map entry denies and nothing else happens | **Enforced in code** | no sentinel call, no heartbeat, no usage post (test) |
| An agent absent from the map is never touched | **Enforced in code** | sessions are listed per mapped agent and re-checked on `agent.id` (tests, including a listing that ignores the filter) |
| The key never leaves the process | **Enforced in code** | read from a file per poll, passed only to `anthropic.Anthropic(api_key=...)`; errors carry exception class names and status codes, never `str(exc)`; test: a sentinel key string is absent from `/health`, `/stats`, every `/halt` answer and the logs, also when the client factory raises with the key in its message |
| Estate secrets never leave the outbound header | **Enforced in code** | read from `secret_file` on every sentinel, heartbeat and usage request; tests: per-agent URL + header, env-default agent untouched, the local `FIELD_SHARED_SECRET` never sent to another estate, missing/blank file denies, a rotation between two calls of one batch is honoured, a URL with credentials is refused, file content absent from every response |
| Confirmations only for `ask` events, and at most once | **Enforced in code** | `allow`/`deny`/absent `evaluated_permission` never confirmed; an event confirmed by anyone (a `user.tool_confirmation` naming it) or by this process is not answered again across ticks or across a restart (tests) |
| Only the calls the session is waiting on are answered | **Enforced in code** | when the `requires_action` idle carries `stop_reason.event_ids`, only listed asks are checked; an earlier, unlisted ask (interrupted turn) is dropped for good (tests: the reviewer's stale + fresh repro, and a stale ask read on an earlier tick) |
| A confirmation the API rejects is not retried forever | **Enforced in code** | a 4xx on a single-event send is terminal (`confirm_rejected`): no new sentinel check, no re-send (test: 6 ticks -> 1 check); 5xx, transport, 408 and 429 are retried next tick; a failing batch is split only on a 4xx |
| Usage posts are deltas with a restart-safe cursor | **Enforced in code** | tests: two snapshots -> two deltas; a restart with the cursor file -> no re-post; governor 404 -> cursor unchanged and retried; the file is written before the in-memory cursor advances, so a failed write re-posts next tick instead of losing the delta from disk; a corrupt cursor disables posting rather than re-posting history |
| `/halt` needs the origin header and never force-archives | **Enforced in code** | 403 without `x-field-kill-origin: kill-switch` (nothing listed); only `idle`/`terminated` are archived; still `running` or `rescheduling` at the deadline -> `archived: false`, no archive call (tests) |
| The origin header is authentication | **Declared only: it is a marker, not authentication** | same as the X3 canary (`packages/field-agent/.../canary.py`). `/halt/<mapped id>` is EXEMPT from the `x-field-auth` perimeter because the kill-switch's outbound signal carries no `x-field-auth` (`kill_switch/api.py`, the headers dict at the outbound call). Anything on the compose network that can reach `approver:8014` can halt (interrupt + permanently archive) a mapped agent's sessions. The exempt paths are computed at app start: an agent added to the map later needs an approver restart before its `/halt` is reachable without the perimeter header |
| A `bash` call is a classified action | **Declared only** | it is one FIELD scope string (`run commands in sandbox`, Don's P27 decision 5); the sentinel sees the action string, never the command text or tool input. The sandbox is the blast radius |
| Approval latency | **Declared only** | v0 polls (no webhooks): a call waits up to one poll interval plus the sentinel round trip; an idle session whose `updated_at` has not moved is re-read at most every 60 s, so a change the API does not reflect in `updated_at` can wait up to 60 s. Not measured until the GB10 run |
| The verdict is right for the agent | **Declared only** | it is as good as the token and agent map the operator wrote (the map is trusted: whoever writes it chooses the FIELD identity, token and estate for a Console agent) |
| Archive is reversible | **Declared only: it is not** | `sessions.archive` is permanent (no unarchive); `/halt` archives |
| Agents that are not `always_ask` are governed | **Declared only: they are not** | an `always_allow` tool, an `auto` call the server allows or denies, `web_search`/`web_fetch` (domain lists only) never reach this service |
| A session blocked on a custom tool progresses | **Declared only: it does not** | v0 executes no custom tool; such a session stays idle (fail closed). Custom-tool execution is the next slice |
| Sentinel `log_only` mode is enforcement | **Declared only** | in `log_only` the sentinel answers ALLOW for everything (shadow-ledgered); the approver then allows and records `shadowed: true`. The GB10 runs `enforce` |
| The live Managed Agents shapes | **Declared until the GB10 run** | field names verified against the SDK source at v2.3.0 (SPEC.md) and the claude-api skill docs; every test runs against a fake client. Not yet run against the real API |
| The sandbox holds no FIELD secret | **Declared only (S1 weakness)** | on the self-hosted GB10 sandbox the agent's own `FIELD_SHARED_SECRET` lives in the sandbox environment; S3 (vault `environment_variable` credential, cloud sandbox) removes it. Not touched here |

## LIMITS

- **The kill-switch's 2 s endpoint timeout.** `/halt` sends every interrupt first, then waits up
  to 20 s per session for `idle` before archiving. The kill-switch's outbound call times out at
  2 s (`ENDPOINT_TIMEOUT_S`), so a halt that has to wait ledgers `kill.endpoint_failed` there
  while the approver still completes it. The registry flip already makes the next sentinel
  `/check` a BLOCK, so the next tool call is denied whatever the signal outcome.
- **Halts reach only GB10 agents.** An agent routed to another estate (`estate_base_url`, e.g.
  Fly) cannot be halted by that estate's kill-switch through this endpoint (the GB10 is not
  reachable from Fly); its kill still turns every later `/check` into a BLOCK.
- **Cache-creation tokens are not metered.** The governor's `UsageRequest` has no field for them
  (`extra="forbid"`); `session.usage.cache_creation` is dropped. Session runtime (USD 0.08/h) is
  not metered either.
- **Heartbeats are the approver's.** A check-in is posted per handled call on the agent's
  behalf, so `/liveness` shows the approver handling that agent's calls, not the agent's process.
- **Rate budget.** Per tick: one `sessions.list` per mapped agent (plus pages) and one
  `events.list` per idle session that changed (or every 60 s); Managed Agents allows 600 RPM
  per organization for these endpoints.
- **Multiagent sessions.** Cross-posted subagent calls are answered under the session's mapped
  (primary) FIELD identity; the subagent's own Console agent is not looked up. That
  `requires_action.event_ids` names the cross-posted event ids is unverified until the live run.
- **A rejected confirmation strands its call.** After a terminal 4xx the session keeps waiting on
  that event (fail closed); `confirm_rejected` on `/stats` is the signal to look at it in the
  Console.
- **An approver outage freezes sessions** (`requires_action` waits indefinitely): fail closed,
  and a stuck fleet needs a watcher (evaluation R3).
- API authn: optional shared-secret header (`FIELD_SHARED_SECRET` -> `x-field-auth`), enforced by
  middleware when set; `/health` and the mapped `/halt/<id>` paths stay open. Plain HTTP on the
  compose network; TLS to a remote estate is the URL's `https`.
