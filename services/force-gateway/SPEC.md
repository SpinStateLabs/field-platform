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
  (`FORCE_GATEWAY_MOCK=1` exactly / `--mock`) so demos/tests need no secrets;
  keyless real upstream answers 502 naming `ANTHROPIC_API_KEY`.
- Telemetry: regex counters (confidence tags, corrections, flattery, CoT
  structure, objections, source honesty) + usage + latency; `GET /telemetry`
  aggregate with per-route rates over `all` / `last_N` windows; every payload
  labeled heuristic.
- v1.2 D2: persistent SQLite telemetry under `$FIELD_DATA_DIR/gateway/`
  (records, append-only drift scores replayed at startup, counters);
  drift keyed by `(route, dimension)` (`overall`, `sycophancy`); platform
  judge traffic (`x-force-passthrough: judge`, gated by `x-field-auth` on
  secret estates, ledgered on secretless ones) forwarded uninstrumented —
  but a passthrough naming an agent (`x-field-agent-id`) is still metered to
  the governor.
- CLI: `forcegw presets | telemetry | serve [--mock]`.

**Explicit non-goals (v0.1)**
- No streaming interception; no non-Anthropic API shapes.
- No enforcement of FORCE compliance (measurement only).
- No dashboards beyond the JSON endpoint (telemetry persists since v1.2 D2).
- No key management — env vars only, never stored.
