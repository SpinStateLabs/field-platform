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

## ADR 10 delta — sampled judge, trend alerts, fail-open + capped

- **Sampled hygiene judge** (`FORCE_HYGIENE_JUDGE=off|mock|anthropic`,
  default OFF; unrecognized → off): scores sycophancy / premise-rigor /
  overall on a pinned cheap model (`claude-haiku-4-5-20251001`,
  `FORCE_HYGIENE_JUDGE_MODEL` override) against a versioned rubric
  (`hygiene-v1`). Sampling is **deterministic 1-in-N**
  (`FORCE_GATEWAY_SAMPLE_EVERY`, default 10, 0=off) — not random, on
  purpose: reproducible and honest. Per-item judge noise is acceptable
  because consumers read aggregates and trends (the mirror image of the
  Sentinel's per-item determinism).
- **Trend alerts, never points:** judged scores aggregate into count-based
  windows per route (= preset; `FORCE_HYGIENE_WINDOW`, default 5); the first
  2 windows fix the baseline; an alert fires ONLY on two consecutive windows
  outside `baseline ± FORCE_HYGIENE_BAND` (0.15), re-arming after a window
  back in band. Judge-model or rubric change resets the baseline (scores
  across judges are not comparable). Alerts ledger as `gateway.drift_alert`.
- **Fail-open + capped:** instrumentation faults or gateway overhead >
  `FORCE_GATEWAY_LATENCY_BUDGET_MS` (250) drop the Gateway to bypass —
  traffic forwards **uninstrumented** for `FORCE_GATEWAY_BYPASS_COOLDOWN`
  requests (10), `gateway.bypass` is ledgered on entry, and every gap lands
  in `/telemetry`'s `coverage` block — never silent. The judge is separately
  gated on the Gateway's OWN spend cap (agent `force-gateway`): governor
  down / no cap / budget BLOCK skips the judgment only (structural telemetry
  continues) and counts `judge_bypassed[reason]`.
- **Self-governance:** `self_manifest.yaml` (inspect: `forcegw
  self-manifest`) names the Founder & CTO as owner, restricts scope to
  observer verbs, and declares the judge budget (USD 5/daily) — apply with
  `governor set-cap force-gateway --from-manifest <path>`.

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Every proxied call carries the preset's FORCE block | **Enforced in code** | injection before forward; tests pin verbatim protocol lines per preset |
| The caller's own system prompt survives injection | **Enforced in code** | string and block-list forms tested |
| Telemetry figures are deterministic | **Enforced in code** | pure regex; labeled on every payload |
| Token spend reaches the governor | **Enforced in code** (best-effort delivery) | usage forwarded per call with agent id |
| The Gateway fails OPEN — its own faults never block traffic | **Enforced in code** | instrumentation exceptions and latency-budget breaches serve the response and enter bypass (tests) |
| Bypass windows are visible, never silent | **Enforced in code** | coverage counters in /telemetry + `gateway.bypass` ledger event on entry (tests) |
| Drift alerts fire only on two consecutive out-of-band windows | **Enforced in code** | drift tests: single-window noise and recovery never alert; one alert per episode |
| Judge spend is capped by the Gateway's own manifest budget | **Enforced in code** | spend gate on agent `force-gateway` before every judgment; no cap / BLOCK ⇒ skip + counted (tests) |
| Judge default OFF; a flag typo cannot enable an LLM in the loop | **Enforced in code** | `resolve_hygiene_judge` unrecognized → off (test) |
| Telemetry stores metadata and scores, not content | **Enforced in code** | records hold counters + tokens only; no response text is retained |
| Judge scoring quality equals human hygiene judgment | **Declared only** | mock proves control flow; ADR 10 names quarterly human calibration of samples |
| The model *obeys* the FORCE block | **Declared only** | injection ≠ compliance; telemetry *measures* surface markers, it cannot force behavior |
| Telemetry counters equal true FORCE compliance | **Declared only** | heuristics: a response can hit every marker and still be wrong |
| Agents route their LLM calls through the gateway | **Declared only** | same cooperative-perimeter caveat as the sentinel |

## LIMITS

- v0.1 speaks the Anthropic Messages shape only; no streaming (`stream:
  true` is not intercepted — telemetry would miss those responses), no
  OpenAI translation layer.
- Telemetry, drift baselines, and bypass state are in-memory per process
  (restarts reset them) — services are not daemons, so trend alerts are
  session-scoped until the telemetry-persistence backlog item lands. The
  two-window rule and coverage accounting are real, tested logic that
  persistence will feed.
- Bypass windows are unmonitored by design (ADR 10 residual risk): while
  bypassed, traffic is uninstrumented. Bounded by coverage-gap visibility
  and the `gateway.bypass` owner notification.
- The mock upstream is for demos/tests and says so in its model id.
- API authn: optional shared-secret header (`FIELD_SHARED_SECRET` → `x-field-auth`), enforced by middleware when set; off by default for local demos. `/health` stays open for probes. Transport is plain HTTP — TLS belongs to a fronting proxy in real deployments.
