# field-agent

Client SDK: put a Python agent under FIELD governance in a few lines —
sentinel-checked actions, metered LLM usage, kill-switch liveness. A
**client, not an authority**: it adds ZERO new power; every decision is made
server-side, and the SDK's only local capability is refusal (raising before
ungoverned work runs). **FIELD letter:** all five (client edge).
**Exec owner:** CTO.

```python
from field_agent import FieldAgent, ActionBlocked, ActionEscalated, AgentKilled

agent = FieldAgent("invoicing-agent", token_id=TOKEN, heartbeat_max_age=30.0)

@agent.governed("draft invoices")            # hook 1: ACTIONS
def draft_invoice(row): ...

agent.ensure_alive()                         # hook 3: LIVENESS (halts if killed)
resp = client.messages.create(...)
agent.report_usage_from(resp, note="INV-001")  # hook 2: USAGE (strict)
```

## What's here

| Module | Provides |
|---|---|
| `field_agent.FieldAgent` | facade: `check` / `governed` / `report_usage[_from]` / `heartbeat` / `ensure_alive` |
| `field_agent.actions` | pure re-export of `conformance_sentinel.governed` — `Governor`, `@governed`, `ActionBlocked`, `ActionEscalated` (the sentinel's own classes, identity-tested) |
| `field_agent.usage` | `UsageClient`, `extract_usage()` (Anthropic response → token counts), typed report models |
| `field_agent.liveness` | `LivenessClient`, `Heartbeat` |
| `field_agent.errors` | `AgentKilled` ⊃ `HeartbeatUnreachable`, `UsageReportError` ⊃ `NoSpendCapError`, `BootstrapError` |
| `field_agent.bootstrap` | operator-side `register()` / `mint()` — deliberately NOT re-exported; agents don't self-authorize |
| `examples/` | copy-paste `agent_template.py` + one sample per hook + a raw-REST equivalent; `examples/run_all.sh` runs the lot against an ephemeral stack |

## CLI

```
fieldagent version
fieldagent heartbeat AGENT_ID                       # exit 1 killed/unknown/unreachable
fieldagent check AGENT_ID "action" --token-id T     # exit 0 ALLOW / 1 BLOCK / 2 ESCALATE
fieldagent report-usage AGENT_ID --model M --input-tokens N --output-tokens N   # exit 3 on rogue findings
fieldagent mint AGENT_ID --granted-by HUMAN --scope "read timesheets" --ttl-seconds 3600
```

## Enforced vs. Declared

A governance product that overclaims has already failed. This table is exact.

| Guarantee | Status | How |
|---|---|---|
| Actions behind `check()`/`governed()` run only on ALLOW; BLOCK/ESCALATE raise before the callable executes | **Enforced in code** | reused `conformance_sentinel.governed.Governor`; test proves the decorated body never runs on BLOCK |
| Sentinel unreachable ⇒ action blocked | **Enforced in code** | `Governor.check` fail-closed branch, pinned here by `test_adversarial_sentinel_down_blocks` (this branch had no test before this package) |
| Killed or **unknown** agent halts at `ensure_alive()` | **Enforced in code** | kill-switch answers `killed=true` for unknown agents; `AgentKilled` raised; adversarial tests |
| Kill-switch unreachable ⇒ halt | **Enforced in code** | `HeartbeatUnreachable` **subclasses** `AgentKilled` — `except AgentKilled` cannot fail open on an outage |
| Failed or uncapped usage report raises — no silent unmetered spend | **Enforced in code** | strict `report_usage`; governor 404 ⇒ `NoSpendCapError`; tests |
| Every SDK HTTP call carries `x-field-auth` when the secret is set | **Enforced in code** | `auth_headers()` merged per request (`_transport.AuthedClient`); secret-estate test shows a bare client 401s where the SDK succeeds |
| An agent that never calls the SDK is governed | **Declared only** | cooperative perimeter — the SDK adds zero coverage to non-callers; compensation: the sentinel reads the registry on every `/check`, so any governed entry point still gates a killed agent |
| In-flight work stops between heartbeats | **Declared only** | the halt happens at the next `check()`/`ensure_alive()`; latency is bounded by `heartbeat_max_age` or the agent's own cadence, not zero |
| Reported token counts are truthful | **Declared only** | self-reported; route LLM calls through force-gateway `/v1/messages` + `x-field-agent-id` for observed metering |
| `token_id` is valid and scoped for the action | **Declared only** (client-side) | the SDK carries an opaque id; validation is enforced by delegation-authority + sentinel, not here |

## LIMITS

- The SDK is a client, not an authority. It cannot grant, extend, or launder
  power; its only local capability is refusal.
- Self-reported usage trusts the reporter. The force-gateway path removes
  that trust but is optional and documented, not defaulted.
- No background liveness thread — a daemon thread can only set a flag the
  main thread might never read (a Declared guarantee wearing an Enforced
  costume). Liveness is checked lazily; a busy loop that never calls the SDK
  is invisible until its next governed action, which the sentinel still
  blocks post-kill.
- Sync `httpx` only; async agents wrap calls in a thread for v0.1.
- The package depends on `conformance-sentinel` for `governed.py` (reuse,
  never reinvent). That module imports only httpx + field_core, but the
  package dep would pull service deps from an index; the monorepo installs
  with `--no-deps` so only editable-install order matters. Promoting
  `governed.py` into field-core is a v0.2 refactor.
- `bootstrap.register/mint` exist for demos and operators; `granted_by` is a
  recorded string — operator authn is out of v0.1 scope (same line
  kill-switch draws).
