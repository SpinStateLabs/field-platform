# SPEC - claude-approver

**Purpose:** answer every Claude Managed Agents tool call that pauses for approval
(`evaluated_permission: "ask"`) with the conformance-sentinel's verdict; bridge session usage to
the spend-governor; give the kill-switch an agent-side halt endpoint that interrupts and archives
the agent's sessions. A client, not an authority (`docs/INTEGRATION.md` section 1).

**Exec owner:** CISO. **FIELD letter:** E - Enforcement. **Pilot slice:** S2 (evaluation
2026-10-26 section 6). **Status:** v0.1.0, compose profile `approver`, flags OFF, not deployed.

## v0.1 scope

- Polling only (no webhook registration): `tick()` every `CLAUDE_APPROVER_POLL_SECONDS`.
- Sessions per mapped Console agent: `beta.sessions.list(agent_id=...)`; approvals for `idle`
  sessions whose latest `session.status_idle.stop_reason.type == "requires_action"`.
- Pending = `agent.tool_use` / `agent.mcp_tool_use` with `evaluated_permission == "ask"` and no
  `user.tool_confirmation` whose `tool_use_id` is that event's id (anyone's, or this process's).
- Verdict: `POST <sentinel>/check`, 10 s. `allow` only on 200 + JSON object + `decision ==
  "ALLOW"`. Deny messages: `<clause>: <reasons>` (BLOCK), `escalated: a human holds this item;
  <clause>: <reasons>` (ESCALATE), `claude-approver: <reason>` (everything else).
- One `events.send` per session with all its confirmations; on refusal each is retried alone.
- Heartbeat `POST <kill-switch>/heartbeat/<field id>` after each delivered confirmation.
- Usage deltas to `POST <governor>/usage` from `session.usage`, cursor
  `$FIELD_DATA_DIR/claude-approver/usage-cursor.json` (atomic replace), moved only on 201.
- `POST /halt/{field_agent_id}`: origin marker required; interrupt all, then wait/archive.
- Per-agent estate routing (`estate_base_url`, `secret_file`; Don's P28 b).
- Custom tools: parsed from the map, NOT executed; such sessions are left untouched
  (`custom_tool_pending`).
- `/health` (open), `/stats` (perimeter), CLI `approver serve | version`.

## Design decisions

- **The SDK is imported only in `client.make_client`.** CI installs services `--no-deps`; the
  suite asserts `anthropic` is never imported. The image is the only place it is installed.
- **`stop_reason` from events.** `BetaManagedAgentsSession` (v2.3.0) has no `stop_reason`; the
  latest `session.status_idle` event's `stop_reason.type` is used.
- **Events cursor.** `events.list(session_id, created_at_gte=<newest processed_at seen>,
  order="asc")`, deduplicated by event id (the filter is inclusive and compares `processed_at`).
  Queued user events have `processed_at: null` and do not move the cursor.
- **Re-read throttle.** An idle session with nothing pending whose `updated_at` is unchanged is
  re-read at most every 60 s (`EVENTS_REFRESH_SECONDS`), so end-turn sessions that sit idle for
  days do not spend the 600 RPM organization budget.
- **Model id.** The session's own snapshot `session.agent.model.id` (exact for that session,
  no request) first; `agents.retrieve(agent_id).model.id` (cached per tick) when the snapshot has
  none; else `unknown`.
- **Usage fallback.** When a session object carries no `usage`, the newest `session.usage` event
  (`events.list(types=["session.usage"], order="desc", limit=1)`, first item only).
- **Halt ordering.** Every interrupt is sent before any wait, so all sessions get the interrupt
  within the kill-switch's 2 s call even when archiving waits.
- **Perimeter exemption for `/halt/<id>`.** Ruled by the controller (2026-10-26, finding 1): the
  kill-switch's outbound signal carries no `x-field-auth`, so the mapped halt paths are passed to
  `field_core.authn.install(open_paths=...)` at app creation, as for the X3 canary.
- **Unusable entry vs. structural error.** A bad entry (no `field_agent_id`, wrong types, bad
  `estate_base_url`) is kept and its calls are denied (`unmapped`); invalid JSON or a non-object
  empties the whole map (nothing touched).
- **Invalid global tool map denies** (`config_error`) instead of falling back to defaults.
- **A corrupt usage cursor disables usage posting** (`usage_cursor_error`) instead of starting
  from zero, which would re-post every session's history.

## SDK field names: verified against `anthropic` v2.3.0 (pinned `anthropic>=2.3.0`)

Read 2026-10-26 with `gh api` (raw contents at tag `v2.3.0`; PyPI latest, uploaded
2026-10-23T23:18Z). Every URL below is under
`https://github.com/anthropics/anthropic-sdk-python/blob/v2.3.0/`:

| File | What it fixed in this service |
|---|---|
| `src/anthropic/resources/beta/sessions/sessions.py` | `list(agent_id, agent_version, created_at_*, deployment_id, include_archived (default false), limit, memory_store_id, order, page, statuses)` returns `SyncBidirectionalPageCursor` (iterating auto-paginates); `retrieve(session_id)`, `archive(session_id)` |
| `src/anthropic/resources/beta/sessions/events.py` | `list(session_id, created_at_gt/gte/lt/lte (against processed_at), limit, order (default asc), page, types)` returns `SyncPageCursor`; `send(session_id, events=[...])` |
| `src/anthropic/resources/beta/agents/agents.py` | `retrieve(agent_id, version=...)` |
| `src/anthropic/types/beta/beta_managed_agents_session.py` | `id, agent, archived_at, environment_id, status (rescheduling/running/idle/terminated), updated_at, usage, deployment_id`; no `stop_reason` |
| `src/anthropic/types/beta/beta_managed_agents_session_agent.py` | `agent.id`, `agent.model` (`BetaManagedAgentsModelConfig`), `agent.version` |
| `src/anthropic/types/beta/beta_managed_agents_model_config.py` | `model.id` |
| `src/anthropic/types/beta/beta_managed_agents_agent.py` | `model: BetaManagedAgentsModelConfig` |
| `src/anthropic/types/beta/beta_managed_agents_session_usage.py` | `input_tokens, output_tokens, cache_read_input_tokens, cache_creation, list_cost, active_seconds` (all optional) |
| `src/anthropic/types/beta/beta_managed_agents_cache_creation_usage.py` | `ephemeral_1h_input_tokens, ephemeral_5m_input_tokens` (not metered: the governor has no field) |
| `src/anthropic/types/beta/beta_managed_agents_session_usage_event.py` | `type: "session.usage"`, `usage` |
| `src/anthropic/types/beta/sessions/beta_managed_agents_agent_tool_use_event.py` | `id, name, input, processed_at, evaluated_permission, evaluation, session_thread_id` |
| `src/anthropic/types/beta/sessions/beta_managed_agents_agent_mcp_tool_use_event.py` | same plus `mcp_server_name` |
| `src/anthropic/types/beta/sessions/beta_managed_agents_agent_custom_tool_use_event.py` | `id, name, input`; answered by `user.custom_tool_result.custom_tool_use_id` |
| `src/anthropic/types/beta/sessions/beta_managed_agents_user_custom_tool_result_event.py` | `custom_tool_use_id` |
| `src/anthropic/types/beta/sessions/beta_managed_agents_session_status_idle_event.py` | `stop_reason` (union), `processed_at` |
| `src/anthropic/types/beta/sessions/beta_managed_agents_session_requires_action.py` | `type: "requires_action"`, `event_ids` |
| `src/anthropic/types/beta/sessions/beta_managed_agents_user_tool_confirmation_event.py` | `tool_use_id, result, deny_message, processed_at (optional: null while queued)` |
| `src/anthropic/types/beta/sessions/beta_managed_agents_user_tool_confirmation_event_params.py` | send shape `{type: "user.tool_confirmation", tool_use_id, result: "allow"/"deny", deny_message (deny only)}` |
| `src/anthropic/types/beta/sessions/beta_managed_agents_user_interrupt_event_params.py` | `{type: "user.interrupt"}`; no `session_thread_id` = every non-archived thread |
| `src/anthropic/types/beta/sessions/beta_managed_agents_event_params.py` | the union `events.send` accepts |

Behaviour facts (not field names) are from the claude-api skill's Managed Agents files
(`shared/managed-agents-events.md`, `-client-patterns.md` sections 3-6, `-tools.md` Permission
Policies, `-api-reference.md`, `-core.md`, `python/managed-agents/README.md`). `anthropic`
2.3.0 depends on `httpx2` (not `httpx`); the image installs both.

## Tests (`tests/`, pytest, no network, no `anthropic`)

`approver_fakes.FakeConsole` (records every call; refuses a confirmation for a non-`ask` or
already-answered event like the API's 400; echoes sent events) and `FieldServices`
(`httpx.MockTransport` for sentinel, kill-switch, governor). Mutant check: deleting the ALLOW
branch of `_check` fails every test marked `expects_allow` (10 of 10); accepting the decision
case-insensitively fails the `lowercase-allow` and `padded-allow` cases.

## Not verified until the GB10 run

The live API shapes, approve/deny round-trip latency (p50/p95 on `/stats`), running-time cost per
approval, and whether `updated_at` moves on every event that matters.
