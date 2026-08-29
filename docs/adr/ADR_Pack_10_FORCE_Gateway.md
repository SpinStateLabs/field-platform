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

**Alternatives Considered**

| Path | Why Considered / Rejected | What It Would Cost or Expose Us To |
|---|---|---|
| Fail-closed proxy | Rejected: an observability layer must never take down production | One Gateway bug halts every agent |
| Full-content logging | Rejected: creates the privacy exposure FIELD exists to prevent | A breach of the telemetry store becomes a breach of everything |
| **Chosen: fail-open, metadata-only, capped** | Residual risk named: bypass windows are unmonitored | Bounded by coverage-gap visibility and owner notification |

## Economics note (pre-build)

Injection adds ≈ zero marginal cost (configuration). Telemetry cost = sample rate × traffic × judge tokens, on a cheap model class, hard-capped. Proxy latency budget is set in plan mode and enforced by the bypass guardrail. Roadmap position: built second, after the Sentinel PoC gate; dogfoods immediately on Spin State's own traffic.
