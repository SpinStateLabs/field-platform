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
agent.checkin()                              # hook 3: LIVENESS check-in (POST; records last_seen)
resp = client.messages.create(...)
agent.report_usage_from(resp, note="INV-001")  # hook 2: USAGE (strict)
```

## What's here

| Module | Provides |
|---|---|
| `field_agent.FieldAgent` | facade: `check` / `governed` / `report_usage[_from]` / `heartbeat` / `checkin` / `ensure_alive` / `cross` |
| `field_agent.actions` | pure re-export of `conformance_sentinel.governed` — `Governor`, `@governed`, `ActionBlocked`, `ActionEscalated` (the sentinel's own classes, identity-tested) |
| `field_agent.usage` | `UsageClient`, `extract_usage()` (Anthropic response → token counts), typed report models |
| `field_agent.liveness` | `LivenessClient`, `Heartbeat` |
| `field_agent.federation` | `FederationClient` (`FIELD_FEDERATION_URL`), `CrossingBlocked`; `cross()` ASKS federation-broker `POST /crossing` for a decision — it never relays or carries cross-org traffic |
| `field_agent.errors` | `AgentKilled` ⊃ `HeartbeatUnreachable`, `UsageReportError` ⊃ `NoSpendCapError`, `BootstrapError` |
| `field_agent.bootstrap` | operator-side `register()` / `mint()` — deliberately NOT re-exported; agents don't self-authorize |
| `field_agent.canary` | v1.2 X3 canary agent, NOT re-exported: `python -m field_agent.canary serve` (the GB10 `canary-agent` compose service, profile `x3`: `POST /halt`, `GET /status`, `GET /health` on :8090) and `python -m field_agent.canary x3-check --agent canary-gb10` (the X3 live check, run inside the kill-switch container) |
| `examples/` | copy-paste `agent_template.py` + one sample per hook + a raw-REST equivalent; `examples/run_all.sh` runs the lot against an ephemeral stack |

## CLI

```
fieldagent version
fieldagent heartbeat AGENT_ID                       # read-only poll; exit 1 killed/unknown/unreachable
fieldagent checkin AGENT_ID                         # POST a check-in; exit 1 killed/unknown/unreachable
fieldagent check AGENT_ID "action" --token-id T     # exit 0 ALLOW / 1 BLOCK / 2 ESCALATE; a rate-limited BLOCK also prints "retry_after_seconds: N" on stderr
fieldagent cross AGENT_ID --org ORG --scope S --data-class D --manifest m.yaml [--direction outbound|inbound] [--counterparty-agent-id A] [--signature B64]   # exit 0 ALLOW / 1 BLOCK or broker unreachable
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
| A rate-limited BLOCK tells the agent when to retry | **Enforced in code** | `ActionBlocked.retry_after` (the sentinel's own class, re-export identity unchanged) reads the verdict's `retry_after_seconds`, equal to the governor's value; `fieldagent check` prints it and still exits 1 (`tests/test_throttle_sdk.py`) |
| `report_spend(action=…)` feeds that action's rate window; THROTTLED comes back on the returned status | **Enforced in code** | `action` sent only when set (a pre-D1 governor forbids the key); `SpendStatusLite.retry_after_seconds` (`tests/test_throttle_sdk.py`). Every checked action is already counted by the sentinel: report cents for it, not `actions` (option B) |
| Cross-org work behind `cross()` proceeds only on the federation-broker's ALLOW; BLOCK raises `CrossingBlocked` carrying the verdict and clause | **Enforced in code** | `FederationClient.cross`; only an exact `ALLOW` returns (`tests/test_federation_sdk.py`) |
| Federation-broker unreachable or no decision ⇒ crossing refused | **Enforced in code** | `CrossingBlocked(verdict=None)`, 'federation-broker unreachable — failing closed'; no clause invented |
| The cross-org call the agent makes after ALLOW stays inside the envelope it asked about (scope + data class) | **Declared only** | the SDK asks for a decision and returns; it never relays or inspects the traffic that follows, and an agent that crosses without asking is invisible to the broker |
| The outbound manifest `cross()` presents is the agent's registered one | **Declared only** | self-presented; the broker does not check it against the registry's `manifest_ref`, and outbound is not signature-checked |
| Every SDK HTTP call carries `x-field-auth` when the secret is set | **Enforced in code** | `auth_headers()` merged per request (`_transport.AuthedClient`); secret-estate test shows a bare client 401s where the SDK succeeds |
| An agent that never calls the SDK is governed | **Declared only** | cooperative perimeter — the SDK adds zero coverage to non-callers; compensation: the sentinel reads the registry on every `/check`, so any governed entry point still gates a killed agent |
| A check-in makes the agent visible to the kill-switch's `GET /liveness` | **Enforced in code** | `checkin()` POSTs `/heartbeat/{agent}`; tests assert `heartbeat()` writes nothing and `checkin()` records `last_seen`, and that a killed or unknown agent's check-in still answers `killed: true`. Nothing on either estate calls it until the SDK and the skills redeploy |
| A recent check-in means the agent is healthy | **Declared only** | it records that *something* POSTed with that agent id at that instant — not that the process is doing its work, and not that a stale agent is dead |
| In-flight work stops between heartbeats | **Declared only** | the halt happens at the next `check()`/`ensure_alive()`; latency is bounded by `heartbeat_max_age` or the agent's own cadence, not zero |
| Reported token counts are truthful | **Declared only** | self-reported; route LLM calls through force-gateway `/v1/messages` + `x-field-agent-id` for observed metering |
| X3 canary: `POST /halt` without `x-field-kill-origin: kill-switch` changes nothing | **Enforced in code** | 403 for a missing, wrong or reason-only header; `/status` stays `halted: false` and the work loop keeps ticking (`tests/test_canary_agent.py`) |
| X3 canary: a halt answers 200 echoing the nonce from the kill reason, stops the work loop and the process NEVER exits | **Enforced in code** | the halt and the work tick share one lock, so no tick runs after the 200; a real `python -m field_agent.canary serve` subprocess is still running and serving `/status` after two halts; `/status` carries the latest nonce and the first halt's `since` |
| X3 canary: the real kill-switch calls it and the canary reports the kill's nonce | **Enforced in code** (tests); **not yet live** | the real kill-switch app, the real `manifests/canary-gb10.yaml` and `FIELD_KILL_ENDPOINT_ALLOWLIST=canary-agent`, over a real socket (name resolution is the only substitution): kill `x3-<nonce>` ⇒ `called` and `/status` halted with that nonce; revive ⇒ +1 `kill.revive`; drill ⇒ `endpoint_confirmed_ms`; allowlist unset ⇒ never called. On the GB10 only after A6 and `x3-check` exit 0; on Fly not until D7 |
| X3 canary: the halt came from an authorised caller | **Declared only** | `x-field-kill-origin` is a marker, not authentication: anything that can reach `canary-agent:8090` can halt the canary. No published port, so on the GB10 that is the compose network |
| `token_id` is valid and scoped for the action | **Declared only** (client-side) | the SDK carries an opaque id; validation is enforced by delegation-authority + sentinel, not here |

## LIMITS

- The SDK is a client, not an authority. It cannot grant, extend, or launder
  power; its only local capability is refusal.
- Self-reported usage trusts the reporter. The force-gateway path removes
  that trust but is optional and documented, not defaulted.
- `cross()` asks; it does not relay. Outbound crossings skip the signature
  step (the contract key is the counterparty's), so outbound authenticity
  rests on our own registry and deploy controls.
- `retry_after` is advice, not a timer: the SDK never sleeps or retries on
  its own, and a retry after it can still BLOCK if other callers of the same
  action filled the window meanwhile.
- A token burst BLOCKs every checked action, not just LLM calls. With a
  usage policy `token_rate_limit` (the plugin's `bootstrap_operator.py`
  installs 200 000 tokens/hour), `report_usage` rows that exhaust the window
  make the governor THROTTLED for every action, so behind an enforcing
  sentinel each `check()` raises `ActionBlocked` (`E.rate_limit`, with
  `retry_after`) until the window ages out. Before D1 the same burst raised
  `ActionEscalated` (the open `rogue_burst` escalation) until a human
  resolved it; resolving it no longer lifts the BLOCK early.
- No background liveness thread — a daemon thread can only set a flag the
  main thread might never read (a Declared guarantee wearing an Enforced
  costume). Liveness is checked lazily; a busy loop that never calls the SDK
  is invisible until its next governed action, which the sentinel still
  blocks post-kill.
- `checkin()` is still lazy and caller-driven: there is no timer. An agent
  that stops calling it looks stale, and an agent that calls it in a loop
  while doing nothing useful looks live. Stale is a prompt to investigate,
  never proof of death; live is never proof of health.
- `POST /heartbeat/{agent}` exists only on kill-switch v1.2 and later.
  Both estates run pre-v1.2 images today, so a check-in there returns 405
  and `checkin()` raises `HeartbeatUnreachable` (fail closed) until Don
  redeploys — use `heartbeat()`/`ensure_alive()` as the halt gate there.
- **The X3 canary's halt is sticky and proves the canary only.** A kill-switch
  `/revive` flips the registry, not the process: `canary-agent` stays halted
  until its container restarts. `outcome: called` plus `/status` halted with
  the kill's nonce proves the signal path to THIS process; it says nothing
  about whether a business agent that receives a signal stops. Heartbeat
  polling is off by default and, when on, halts on an unreachable
  kill-switch too (fail closed), which a kill-switch restart triggers.
- Sync `httpx` only; async agents wrap calls in a thread for v0.1.
- The package depends on `conformance-sentinel` for `governed.py` (reuse,
  never reinvent). That module imports only httpx + field_core, but the
  package dep would pull service deps from an index; the monorepo installs
  with `--no-deps` so only editable-install order matters. Promoting
  `governed.py` into field-core is a v0.2 refactor.
- `bootstrap.register/mint` exist for demos and operators; `granted_by` is a
  recorded string — operator authn is out of v0.1 scope (same line
  kill-switch draws).
