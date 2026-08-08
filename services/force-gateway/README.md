# force-gateway

Reverse proxy for the **Anthropic Messages API shape** that injects the
FORCE runtime protocol as a system block and records deterministic hygiene
telemetry. **FORCE** side of the Force Field Protocol. Exec owners:
**CTO / CDO**.

The protocol text is vendored **verbatim** from the shipped Force-Field
plugin (`plugins/force/skills/force/protocol.md`) — the gateway composes
presets from it and authors no FORCE language of its own:

| Preset | Components |
|---|---|
| `analysis` | F+O+R+C+E (full protocol) |
| `brainstorm` | F+C+E |
| `draft` | F+C |
| `audit` | F+R+C+E |

## API & CLI

`POST /v1/messages` (headers: `x-force-preset`, optional `x-field-agent-id`)
· `GET /presets[/{name}]` · `GET /telemetry` · `GET /health`

```
forcegw presets [--show analysis]
forcegw telemetry
forcegw serve [--port 8009] [--mock]     # --mock: deterministic upstream, no API key
```

Point any Anthropic SDK at the gateway:
`ANTHROPIC_BASE_URL=http://127.0.0.1:8009` — calls proxy through with the
FORCE block prepended; your API key stays in *your* environment
(`ANTHROPIC_API_KEY`), never in this repo.

## Telemetry (labeled heuristic)

Per response, regex counters: confidence tags (`[HIGH]/[MEDIUM]/[LOW]`),
corrections issued, flattery hits (protocol violations), chain-of-thought
structure (`ASSUMPTIONS/REASONING/CONCLUSION`), objection markers, source-
honesty markers, token usage, latency. `GET /telemetry` aggregates. Every
payload carries the method label: *regex heuristic v0.1 — surface markers
only, no semantic judgment, no LLM*.

With `x-field-agent-id` set and a governor configured, token usage is
reported to spend-governor — LLM spend metering without agent cooperation.

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Every proxied call carries the preset's FORCE block | **Enforced in code** | injection before forward; tests pin verbatim protocol lines per preset |
| The caller's own system prompt survives injection | **Enforced in code** | string and block-list forms tested |
| Telemetry figures are deterministic | **Enforced in code** | pure regex; labeled on every payload |
| Token spend reaches the governor | **Enforced in code** (best-effort delivery) | usage forwarded per call with agent id |
| The model *obeys* the FORCE block | **Declared only** | injection ≠ compliance; telemetry *measures* surface markers, it cannot force behavior |
| Telemetry counters equal true FORCE compliance | **Declared only** | heuristics: a response can hit every marker and still be wrong |
| Agents route their LLM calls through the gateway | **Declared only** | same cooperative-perimeter caveat as the sentinel |

## LIMITS

- v0.1 speaks the Anthropic Messages shape only; no streaming (`stream:
  true` is not intercepted — telemetry would miss those responses), no
  OpenAI translation layer.
- Telemetry is in-memory per process (restarts reset it); persistence
  arrives with attestation-reporter's needs in Phase 4.
- The mock upstream is for demos/tests and says so in its model id.
- No API authentication in v0.1 — localhost trust (STATE.md OQ-1).
