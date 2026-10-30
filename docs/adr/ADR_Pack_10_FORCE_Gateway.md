# ADR Package — FORCE Gateway (Initiative #10)

**Spin State Labs · Force-Field platform · Status: design record, pre-build · 2026-08-29 · MIT**
System: an LLM-traffic proxy that injects FORCE runtime constraints across model calls and dashboards the hygiene telemetry — confidence-tag rates, correction frequency, sycophancy drift by route and model. FORCE governs what the AI says; FIELD governs what it is. Buyer: CTO/CDO. Dogfood target: Spin State Labs' own model traffic.
*When committed to `docs/adr/` in SpinStateLabs/Force-Field, this record supersedes the build brief's System 2 section.*

## ADR 1: The Model Decision

**Context.** Two distinct jobs: (a) injecting the FORCE system prompt per route — pure configuration, no model; (b) scoring responses for hygiene — detecting whether confidence tags, corrections, and source references are present (structural) and whether sycophancy or premise-acceptance is drifting (semantic). Simplest class considered: deterministic parsers (regex/AST) over responses — sufficient for structural marker coverage; insufficient for semantic qualities, which require language judgment.

**Decision.** The Gateway is a deterministic proxy with parser-based structural telemetry; semantic hygiene is scored by a *sampled* LLM judge on a small, cheap model class. Injection itself involves no model at all.

- *Bias–variance:* telemetry is consumed as aggregates and trends, not per-item verdicts — so per-item judge noise is acceptable and averages down with sample size. This is the mirror image of the Conformance Sentinel, where per-item reliability forced the deterministic path: the same trade-off, resolved the opposite way because the decision consuming the output is different.
- *Vendor exposure:* the proxy is vendor-agnostic middleware; the judge is prompt-defined and switchable. Main exposure is upstream API/SDK churn — contained by a thin provider adapter.

**Alternatives Considered**

| Path | Why Considered / Rejected | What It Would Cost or Expose Us To |
|---|---|---|
| Judge every call | Rejected: roughly doubles token spend on all traffic for telemetry nobody reads per-item | Cost scales with success; no added decision value |
| Structural parsing only | Rejected: misses the semantic failures FORCE exists to stop | Sycophancy drift invisible — the core promise unmet |
| **Chosen: sampled hybrid** | Cheap, stable aggregates; exact structural coverage | Commits us to sample-rate config, judge rubric maintenance, and drift baselines per route |

## ADR 2: The Decision & Measurement Design

**Context.** Output: per-route hygiene scores and drift alerts. Action triggered: a drift alert sends the route owner to review that route's prompt and configuration. The Gateway is read-only toward traffic — it never blocks a call (see ADR 4).

**Decision.**

- *False positive:* a spurious drift alarm — wasted attention and, repeated, alert fatigue that kills the dashboard's authority.
- *False negative:* real sycophancy drift goes unflagged — the silent failure mode FORCE exists to prevent persists while everyone believes it's handled.
- *Optimization:* against false negatives on **sustained** drift, tolerating single-window noise: alerts fire on two consecutive sampling windows outside the baseline band, never on a single point.
- *Metric:* FORCE marker coverage rate (structural, exact) plus judged hygiene score **trend vs. baseline** (sampled). Not raw accuracy — production traffic has no ground-truth labels; the honest measure is drift-relative, and its calibration is a periodic human scoring of the same samples.

**Alternatives Considered**

| Path | Why Considered / Rejected | What It Would Cost or Expose Us To |
|---|---|---|
| Alert on single-point deviations | Rejected: noisy judge → alarm fatigue | Dashboard ignored within a month |
| Dashboards only, no alerts | Rejected: unreviewed dashboards die quietly | Drift discovered by incident, not telemetry |
| **Chosen: trend-based alerts** | Accepted gap: the judge's rubric is not a human's judgment of sycophancy | Quarterly human calibration on samples; rubric versioned |

## ADR 3: The Data & Grounding Decision

**Context.** Knowledge needed: the canonical FORCE prompt (`docs/FORCE_PROMPT.txt`), per-route configurations, and baseline score distributions. That is all — and it is small, stable, and versioned.

**Decision.** No retrieval pipeline. The judge is grounded by a fixed, versioned rubric; configuration is version-controlled; telemetry lands in an append-only local store. Retrieval is the right answer when knowledge is large, changing, and citation-bearing (the Sentinel's case) — here it would be over-engineering, and saying so is the grounding decision.

**Alternatives Considered**

| Path | Why Considered / Rejected | What It Would Cost or Expose Us To |
|---|---|---|
| RAG over hygiene guidelines | Rejected: the corpus is a two-page rubric | Complexity with no accuracy gain |
| Fine-tuned judge model | Rejected: freezes the rubric into weights; retraining tax on every revision | Stale judgment presented confidently |
| **Chosen: static versioned rubric** | Smallest thing that works | Commits us to rubric versioning and baseline recomputation on any judge-model change |

## ADR 4: The Risk & Guardrail Decision

**Context — two most material risks.** (1) **Security:** the proxy sees every model call's content — a content-exposure concentration point. (2) **Economic / concentration:** the proxy is a single point of failure in front of *all* model traffic, and the judge adds a metered spend that scales with traffic. Lower priority here: control/governance (the Gateway takes no autonomous action), societal (internal telemetry), ethical (no decisions about people).

**Decision.** The Gateway is an observer, so the guardrail protects the traffic from the observer: the proxy **fails open** — its own failure bypasses it rather than blocking production calls; telemetry stores metadata and scores, not full content, by default; judge spend is hard-capped as a manifest value the Gateway itself must respect.

| Guardrail (one sentence) | On proxy fault, latency over budget, or judge spend at cap, the Gateway drops to bypass mode — traffic flows uninstrumented — and notifies the owner; bypass windows are visible in the coverage metric, never silent. |
|---|---|
| Trigger, action, accountable role | Trigger: fault, latency > budget, or spend ≥ cap. Action: bypass + notify + mark coverage gap. Accountable: Founder & CTO (named role). |

> **Superseded in part (v1.2 F1, added 2026-10-29; the decision above is unchanged).** With `FORCE_GATEWAY_ENFORCE=1` (`1` or another accepted spelling, see note 4 below; default `0` is the observer described above) the gateway enforces identity and authority fail-closed at the egress: `/v1/messages` answers 401 without `x-field-agent-id` and `x-field-token`, asks the sentinel, answers 403 on BLOCK or ESCALATE and 503 (no upstream call) when the sentinel is unreachable, before passthrough and before any bypass window. With `FORCE_GATEWAY_TOOL_CHECK=1` as well, a `tool_use` block the sentinel does not allow is replaced by a refusal text block and ledgered (`gateway.tool_refused`). So "the Gateway takes no autonomous action" holds only in observer mode, and the fail-open guardrail still describes the instrumentation (the bypass window), not enforcement: "the Gateway's own trouble may drop instrumentation, never enforcement" (`services/force-gateway/src/force_gateway/api.py`, the F1 comment before the identity check). See the service README for the current behaviour.

**Alternatives Considered**

| Path | Why Considered / Rejected | What It Would Cost or Expose Us To |
|---|---|---|
| Fail-closed proxy | Rejected: an observability layer must never take down production | One Gateway bug halts every agent |
| Full-content logging | Rejected: creates the privacy exposure FIELD exists to prevent | A breach of the telemetry store becomes a breach of everything |
| **Chosen: fail-open, metadata-only, capped** | Residual risk named: bypass windows are unmonitored | Bounded by coverage-gap visibility and owner notification |

## Economics note (pre-build)

Injection adds ≈ zero marginal cost (configuration). Telemetry cost = sample rate × traffic × judge tokens, on a cheap model class, hard-capped. Proxy latency budget is set in plan mode and enforced by the bypass guardrail. Roadmap position: built second, after the Sentinel PoC gate; dogfoods immediately on Spin State's own traffic.

> **Code and ADR compared (added 2026-10-30, card C-550, reviewer C-531; the text above is unchanged).** Checked against `services/force-gateway/src/force_gateway` on the main branch.
> 1. **The bypass guardrail records an event; it does not notify an owner.** Entering bypass appends a best-effort `gateway.bypass` ledger record and counts the gap in the coverage metric (`api.py:644-652`, `_ledger_event` at `api.py:529-538`); nothing in the service sends a message to anyone. Where the table above says "notifies the owner", read "records in the ledger". (The two code comments that said otherwise were corrected with this note.) Whether to wire notifications through the alerts library in field-core is a feature decision, not made here.
> 2. **At judge spend cap only the judge is skipped.** The sampled hygiene judge is skipped and counted when there is no governor, the governor is unreachable or errors, no cap is set, the budget is reached, or the judge call itself errors (`api.py:669-688`, `judge_bypassed`); structural instrumentation of the traffic continues. Bypass mode proper is entered by a fault or the latency budget, not by the spend cap.
> 3. **`docs/FORCE_PROMPT.txt` does not exist.** The prompt the gateway injects is the vendored `services/force-gateway/src/force_gateway/data/protocol.md` (`presets.py:3-6`), a verbatim copy of the Force-Field repository's `plugins/force/skills/force/protocol.md`.
> 4. **`FORCE_GATEWAY_ENFORCE` is no longer "exactly `1`".** It accepts `1 true yes on` and `0 false no off` (case-insensitive) and an unrecognised value refuses to start (`api.py:290-301`, C-180); only `FORCE_GATEWAY_MOCK` stays exact-match `1`.
> 5. **"Append-only local store" holds for `drift_scores` only.** Telemetry rows are pruned to the newest `max(retain, N)` (`store.py:33` `DEFAULT_RETAIN`, `FORCE_TELEMETRY_RETAIN`); `drift_scores` is append-only (`store.py:11`).
> 6. **Quarterly human calibration is planned, not built.** The code calls judge quality "Declared until the quarterly human calibration" (`hygiene_judge.py:15`); there is no calibration tooling or record in the source or tests.
