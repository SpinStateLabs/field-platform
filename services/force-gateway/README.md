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

`POST /v1/messages` (headers: `x-force-preset`, optional `x-field-agent-id`,
platform-only `x-force-passthrough: judge`) · `GET /presets[/{name}]` ·
`GET /telemetry[?limit=20]` · `GET /health`

```
forcegw presets [--show analysis]
forcegw telemetry                        # target: FIELD_GATEWAY_URL (CLI only)
forcegw serve [--port 8009] [--mock]     # --mock sets FORCE_GATEWAY_MOCK=1
FORCE_GATEWAY_MOCK=1 forcegw serve       # the same, the way compose/demo.sh do it
```

Upstream selection: an injected upstream (tests) > `FORCE_GATEWAY_MOCK`
exactly `1` (deterministic mock, no key) > the real API. Any other value —
`true`, `yes`, ` 1` — is the REAL upstream, which answers **502 naming
`ANTHROPIC_API_KEY`** on `/v1/messages` while no key is set (`/health`,
`/presets`, `/telemetry` need none). The compose stack no longer passes
`--mock` (v1.2 D2): an estate is keyless-real unless its `.env` says
`FORCE_GATEWAY_MOCK=1`.

Point any Anthropic SDK at the gateway:
`ANTHROPIC_BASE_URL=http://127.0.0.1:8009` — calls proxy through with the
FORCE block prepended; your API key stays in *your* environment
(`ANTHROPIC_API_KEY`), never in this repo.

Two gateway URL variables, two meanings:

| Variable | Read by | Meaning |
|---|---|---|
| `FIELD_GATEWAY_URL` | the `forcegw` CLI | where `forcegw telemetry` points |
| `FORCE_GATEWAY_URL` | `field_core.llm` — the sentinel's semantic judge, the crosswalk's suggester, this gateway's hygiene judge | base URL for the PLATFORM's own LLM calls (compose `http://forcegw:8009`, Fly `http://127.0.0.1:8009`); wins over `ANTHROPIC_BASE_URL` |

The gateway's own upstream (`real_upstream`) reads `ANTHROPIC_BASE_URL` only
— never `FORCE_GATEWAY_URL`, which names the gateway itself.

## Telemetry (labeled heuristic)

Per response, regex counters: confidence tags (`[HIGH]/[MEDIUM]/[LOW]`),
corrections issued, flattery hits (protocol violations), chain-of-thought
structure (`ASSUMPTIONS/REASONING/CONCLUSION`), objection markers, source-
honesty markers, token usage, latency. `GET /telemetry` aggregates. Every
payload carries the method label: *regex heuristic v0.1 — surface markers
only, no semantic judgment, no LLM*.

With `x-field-agent-id` set and a governor configured, token usage is
reported to spend-governor — LLM spend metering without agent cooperation.
That includes `x-force-passthrough` calls (note `force-gateway LLM call
(passthrough)`); it excludes bypass windows, which forward uninstrumented.

**Rates (v1.2 D2a).** `/telemetry` keeps every count above and adds
`rates: {route: {window: RouteRates}}` — route = preset, plus `_all` across
routes; windows `all` (every instrumented request since the store was
created) and `last_N` (the newest N, count-based, N =
`FORCE_TELEMETRY_WINDOW`, default 50 — deterministic, no clock). Each
`RouteRates` carries the method label, `window_size`, `requests`, and
`confidence_tag_rate` / `flattery_free_rate` / `cot_structure_rate` — **`null`,
not 0.0, when the window holds no requests** (no data is not a bad score).

**Persistence (v1.2 D2c).** Telemetry lives in
`$FIELD_DATA_DIR/gateway/telemetry.sqlite3` (`./var/...` when unset):
`telemetry_records` (metadata + counters, never response text; the newest
`max(FORCE_TELEMETRY_RETAIN, FORCE_TELEMETRY_WINDOW)` rows are kept, default
10000, plus each route's own newest `FORCE_TELEMETRY_WINDOW` rows so every
route's `last_N` stays exact), append-only `drift_scores(route, dimension, score, model, rubric, ts)`
replayed into the drift tracker at startup, and `counters` (the sampling
stride, the coverage counters, and the cumulative per-route aggregates behind
the totals and the `all` window — pruning never shrinks a total). One
instrumented request is one transaction. `bypass_remaining` is not persisted:
a restart re-arms instrumentation. A store that cannot open or write is an
instrumentation fault like any other — the call answers 200, the gateway
bypasses with reason `store_fault`, `/telemetry` answers 503 with the
in-memory coverage block, and `/health` reports `telemetry_store` (`error`
until a later commit succeeds). A request whose commit fails leaves no trace
in memory either: its sampling-stride slot is released and its coverage
counters are applied only after the commit, so the running process never
disagrees with what a restart would load (a judgment made just before a failed
commit is lost, but its tokens were already metered on the gateway's cap).

**Platform passthrough (v1.2 D2e).** The platform's own judge calls (sentinel
semantic judge, crosswalk suggester, this gateway's hygiene judge) carry
`x-force-passthrough: judge` when `FORCE_GATEWAY_URL` routes them here. The
gateway forwards such a call **uninstrumented** — no FORCE injection, no
telemetry record, no sampling (a judged sample's own judge call can never be
judged) — and counts it in `coverage.passthrough`. It does not consume a
bypass window. **Passthrough is not a metering exemption:** a passthrough that
carries `x-field-agent-id` is still reported to the governor (`/usage`, note
`force-gateway LLM call (passthrough)`), so no agent can switch off its token
metering with the header. The platform judges send no agent id, so their calls
are not reported here — each meters its own cap (the hygiene judge on agent
`force-gateway`) and nothing is counted twice. With
`FIELD_SHARED_SECRET` set the header is honoured only alongside a valid
`x-field-auth` (the handler checks it too, not only the perimeter
middleware); an unrecognised value or an unauthenticated passthrough is
instrumented and counted like any call. On a secretless estate it is honoured
and every passthrough is ledgered `gateway.passthrough{client_host, agent_id}`.
**Platform judge traffic is deliberately excluded from hygiene telemetry.**

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
  windows per series (`FORCE_HYGIENE_WINDOW`, default 5); the first
  2 windows fix the baseline; an alert fires ONLY on two consecutive windows
  outside `baseline ± FORCE_HYGIENE_BAND` (0.15), re-arming after a window
  back in band. Judge-model or rubric change resets every series of the
  route (scores across judges are not comparable). Alerts ledger as
  `gateway.drift_alert`.
- **Per-dimension drift (v1.2 D2b):** a series is `(route, dimension)`; each
  judgment feeds two — `overall` and `sycophancy` — with independent
  baselines, so sycophancy can drift while overall holds and the alert names
  the dimension (`gateway.drift_alert{route, dimension, …}`). `/telemetry`
  `hygiene_trend` nests `{route: {dimension: state}}`; `active_alerts` is
  `[{route, dimension}]`. **With the judge off — both estates today — there is
  no sycophancy signal at all:** the mechanism is enforced in code, the
  signal exists only where `FORCE_HYGIENE_JUDGE` is on and budgeted.
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
| Token spend reaches the governor | **Enforced in code** (best-effort delivery) | usage forwarded per call with agent id, `x-force-passthrough` calls included (`tests/test_d2_upstream_passthrough.py`: passthrough + agent id ⇒ exactly one `/usage`, secret and secretless); not during a bypass window, which forwards uninstrumented |
| The Gateway fails OPEN — its own faults never block traffic | **Enforced in code** | instrumentation exceptions and latency-budget breaches serve the response and enter bypass (tests) |
| Bypass windows are visible, never silent | **Enforced in code** | coverage counters in /telemetry + `gateway.bypass` ledger event on entry (tests) |
| Drift alerts fire only on two consecutive out-of-band windows | **Enforced in code** | drift tests: single-window noise and recovery never alert; one alert per episode |
| Judge spend is capped by the Gateway's own manifest budget | **Enforced in code** | spend gate on agent `force-gateway` before every judgment; no cap / BLOCK ⇒ skip + counted (tests) |
| Judge default OFF; a flag typo cannot enable an LLM in the loop | **Enforced in code** | `resolve_hygiene_judge` unrecognized → off (test) |
| Telemetry stores metadata and scores, not content | **Enforced in code** | records hold counters + tokens only; no response text is retained — the persisted SQLite file is checked for the mock's response text (`tests/test_d2_store.py`) |
| Hygiene rates per route and `_all`, over `all` and `last_N`; `null` (not 0.0) for an empty window | **Enforced in code** | `tests/test_d2_rates.py`: mixed responses ⇒ 0.5, zero requests ⇒ `null`, an all-bad route ⇒ 0.0, `last_N` slides while `all` keeps history, pruning never shrinks a total, and a quiet route's `last_N` survives pruning by a busy route |
| Drift alerts per `(route, dimension)` — `overall` and `sycophancy`, independent baselines, exactly one alert per episode per series | **Enforced in code** (mechanism) | `tests/test_d2_drift_dimensions.py` + the updated delta tests (exact counts per dimension, never `>= 1`) |
| A sycophancy drift signal exists on the estates | **Declared only** | the hygiene judge is OFF on both estates; no judgments ⇒ no series. Needs `FORCE_HYGIENE_JUDGE=anthropic`, a key, and the gateway's own cap |
| Telemetry, drift baselines, alert state, sampling stride and coverage survive a gateway restart | **Enforced in code** | `tests/test_d2_store.py`: a second `create_app` on the same data dir resumes all of them — `passthrough` and every `judge_bypassed` reason included — re-ledgers nothing, and two data dirs stay isolated; `demo.sh` step 6 restarts a real process. On the estates: Declared until the D-gate restart check (needs the D1 key) |
| A telemetry-store fault never fails traffic | **Enforced in code** | corrupt or closed store ⇒ 200 + bypass `store_fault`, `/telemetry` 503 with coverage (tests) |
| A failed commit leaves the running process equal to its store | **Enforced in code** | a commit that fails after a sampled judgment releases its stride slot and applies no coverage; in-memory stride, coverage and drift state equal a restart's, and `/health` returns to `ok` after the next good commit (`tests/test_d2_store.py`) |
| Platform judge traffic is excluded from hygiene telemetry, and a nested judge cannot re-sample | **Enforced in code** | `x-force-passthrough: judge` forwarded untouched, counted in `coverage.passthrough`, never in `by_preset`; the real `AnthropicHygieneJudge` calling an in-process gateway leaves `total_requests == 1` and the stride unchanged (`tests/test_d2_upstream_passthrough.py`) |
| Passthrough cannot be claimed without the perimeter secret on a secret estate | **Enforced in code** | middleware 401 first; with the middleware removed the handler still instruments an unauthenticated passthrough (tests) |
| Every passthrough on a secretless estate is ledgered | **Enforced in code** (best-effort delivery, like every gateway ledger event) | `gateway.passthrough{client_host, agent_id}` (tests) |
| `x-force-passthrough` cannot switch off an agent's token metering | **Enforced in code** (best-effort delivery) | a passthrough naming an agent is reported to the governor exactly once, `/spend` fallback on a 404 (tests); a passthrough naming NO agent is not metered here — that is the platform judges' own shape |
| The platform's own LLM callers use `FORCE_GATEWAY_URL` > `ANTHROPIC_BASE_URL` > default, and send `x-field-auth` only to `FORCE_GATEWAY_URL` | **Enforced in code** | `field_core.llm` + `tests/test_d2_llm_callers.py` (sentinel judge, crosswalk suggester, hygiene judge: precedence, headers, 200 through a secret gateway); the gateway's own upstream ignores `FORCE_GATEWAY_URL` (test) |
| The estates route platform judge calls through the gateway | **Declared only** | needs `FORCE_GATEWAY_URL` in the compose anchor / Fly entrypoint (integration step) and a deploy; with the judges off on both estates there is no such traffic today |
| A near-miss `FORCE_GATEWAY_MOCK` value never mocks | **Enforced in code** | `true`/`yes`/` 1`/`0`/blank ⇒ real upstream, keyless 502 (tests) |
| Judge scoring quality equals human hygiene judgment | **Declared only** | mock proves control flow; ADR 10 names quarterly human calibration of samples |
| The model *obeys* the FORCE block | **Declared only** | injection ≠ compliance; telemetry *measures* surface markers, it cannot force behavior |
| Telemetry counters equal true FORCE compliance | **Declared only** | heuristics: a response can hit every marker and still be wrong |
| Agents route their LLM calls through the gateway | **Declared only** | same cooperative-perimeter caveat as the sentinel |

## LIMITS

- v0.1 speaks the Anthropic Messages shape only; no streaming (`stream:
  true` is not intercepted — telemetry would miss those responses), no
  OpenAI translation layer.
- Telemetry persists per data dir (v1.2 D2c), but `recent` and the `last_N`
  windows read only the retained rows — the newest `max(FORCE_TELEMETRY_RETAIN,
  FORCE_TELEMETRY_WINDOW)` (default 10000) plus each route's newest
  `FORCE_TELEMETRY_WINDOW`; older rows are deleted. A route's `last_N` holds
  fewer than N only while that route has had fewer than N requests (its
  `requests` says how many). Totals and `all` are cumulative counters and do
  not shrink.
- `drift_scores` is append-only and never pruned; startup replay time grows
  with the number of judged samples (judge-on estates only).
- A telemetry store that cannot open stays unavailable until the process is
  restarted on a repaired file: every instrumented attempt faults and
  bypasses again after each cooldown (visible, never silent).
- On a secretless estate ANY client can self-exempt from hygiene telemetry
  (injection, telemetry, sampling — not metering) with
  `x-force-passthrough: judge`; each such request is ledgered
  `gateway.passthrough{client_host, agent_id}`, where `agent_id` is the
  caller's own unauthenticated `x-field-agent-id` (or null). On a secret
  estate the exemption is exactly as strong as the shared secret (all holders
  are equal) and passthroughs are not ledgered: one that names an agent still
  reaches the governor as usage (whose `usage.recorded` event names the
  agent); one that names no agent leaves only `coverage.passthrough`.
- An `x-field-agent-id` is caller-declared: a client that omits it is not
  metered here on any path (passthrough or instrumented), as before D2.
- If the platform judges ever send their own agent ids on passthrough calls
  (the Phase F exemption), the gateway's hygiene judge would be metered twice
  (its own `force-gateway` report after each judgment, plus the passthrough's);
  that change must drop one of the two reports.
- With `FORCE_GATEWAY_URL` set in its own environment, the gateway's hygiene
  judge calls this same process (as passthrough): one extra worker per judged
  sample, and a judge-on gateway fails its judgments (counted
  `judge_bypassed.error`) if it cannot reach itself.
- The platform callers still require `ANTHROPIC_API_KEY` in THEIR environment
  to construct; routed through the gateway, the key actually used upstream is
  the gateway's, and a keyless gateway answers them 502.
- Bypass windows are unmonitored by design (ADR 10 residual risk): while
  bypassed, traffic is uninstrumented. Bounded by coverage-gap visibility
  and the `gateway.bypass` owner notification.
- The mock upstream is for demos/tests and says so in its model id.
- API authn: optional shared-secret header (`FIELD_SHARED_SECRET` → `x-field-auth`), enforced by middleware when set; off by default for local demos. `/health` stays open for probes. Transport is plain HTTP — TLS belongs to a fronting proxy in real deployments.
