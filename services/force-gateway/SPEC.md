# SPEC — force-gateway

**Purpose:** Put the FORCE runtime protocol in the request path: a reverse
proxy for the Anthropic Messages API shape that injects the preset system
block (composed verbatim from the shipped plugin's protocol.md), preserves
the caller's own system prompt, forwards, and records deterministic hygiene
telemetry per response — with LLM token spend reported to spend-governor.

**Exec owners:** CTO / CDO.

**Protocol side:** FORCE (runtime); composes with FIELD (design-time).

**v0.1 scope**
- `POST /v1/messages` with `x-force-preset` (analysis/brainstorm/draft/audit)
  and optional `x-field-agent-id` for spend attribution.
- Preset blocks parsed from vendored `protocol.md` — no authored FORCE text.
- Injection preserves existing `system` (string or content-block list).
- Upstream: real Anthropic API (key from env only) or deterministic mock
  (`FORCE_GATEWAY_MOCK=1` / `--mock`) so demos/tests need no secrets.
- Telemetry: regex counters (confidence tags, corrections, flattery, CoT
  structure, objections, source honesty) + usage + latency; `GET /telemetry`
  aggregate; every payload labeled heuristic.
- CLI: `forcegw presets | telemetry | serve [--mock]`.

**Explicit non-goals (v0.1)**
- No streaming interception; no non-Anthropic API shapes.
- No enforcement of FORCE compliance (measurement only).
- No telemetry persistence; no dashboards beyond the JSON endpoint.
- No key management — env vars only, never stored.
