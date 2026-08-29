# ADR Package — Conformance Sentinel (Initiative #2 · FIELD v1.1)

**Spin State Labs · Force-Field platform · Status: design record, build in progress · 2026-08-29 · MIT**
System: an agent that continuously audits deployed AI agents against their FIELD governance manifests and blocks non-conforming actions — scope breaches, expired authority, missing ledger writes — at the policy-enforcement point, before they execute. Buyer: CISO. This system is the public "enforcement in v1.1" commitment on spinstatelabs.ca/field.
*This is the repo-facing copy of the ADR package authored for the UWaterloo AI-CTO Deliverable B (source of truth for grading: that document; source of truth for building: this file, once committed to `docs/adr/` — it supersedes the build brief's System 1 section.)*

## ADR 1: The Model Decision

**Decision.** A deterministic policy engine is the primary evaluator; a commercial LLM is invoked by API only for semantic scope judgments the rules cannot resolve — no training, no self-hosting.

- *Simplest class considered:* no model at all — deterministic evaluation of structured manifest fields (scope lists, authority expiry, spend caps, required ledger writes). Sufficient for structural conformance; insufficient for natural-language scopes ("client billing communications only").
- *Bias–variance:* enforcement demands low-variance, auditable behaviour; the high-variance LLM judgment is confined to a narrow, escalate-on-uncertainty role. Flexibility traded for reproducibility, deliberately.
- *Vendor exposure:* judge is stateless and prompt-defined (initially Anthropic); pinned versions, provider abstraction, golden-set regression on swap. The deterministic engine has no vendor dependency.
- *Alternatives rejected:* LLM-judges-everything (~100× cost, non-reproducible, no audit trail); rules-only (semantic breaches undetected). Chosen path commits us to: manifest schema versioning, engine maintenance, a golden test set, swap regression.

## ADR 2: The Decision & Measurement Design

**Decision.** Output = allow / block / escalate per action, each citing its manifest clause. Block halts pre-execution and notifies the owner; escalate pauses for a human.

- *False block* (conforming action halted): operational delay + eroded trust → owners route around governance. *False allow* (breach executes): the incident the product exists to prevent; existential for credibility.
- *Policy — asymmetric by tier:* structural violations hard-block (deterministic, near-zero false blocks by construction; optimize against false negatives); semantic judgments fail to escalate (optimize against false positives under uncertainty); allow only on affirmative conformance.
- *Metrics:* seeded-violation catch rate (gate ≥ 95%, proposed) + live false-block rate (gate ≤ 2%, proposed); ratified at PoC exit. Raw accuracy is decorative here — conformant actions dominate, so always-allow scores >99%.
- *Accepted gap:* judge optimizes a general objective; eval uses seeded violations; deployment cares about client-specific costs. Drift among the three is monitored by ledger review cadence and periodic re-seeding.

## ADR 3: The Data & Grounding Decision

**Decision.** Retrieval over the estate's manifests and referenced policies; no fine-tuning.

- *Why:* manifests are per-agent, per-client, and change on redeploy — wrong to freeze into weights; verdicts must cite the exact current clause (auditor requirement); updates are re-index-on-merge.
- *Pipeline:* clause-level chunking (structure-following) → one index per tenant (isolation is a tested property) → action descriptor + agent identity retrieves candidate clauses, re-ranked by action type → short prompt (descriptor + clauses + rubric) → verdict with citation. Short inputs keep per-call cost low.
- *Access:* per-tenant indexes; Sentinel reads under read-only authority; manifest owner keeps content current via version control.
- *Alternatives rejected:* long-context stuffing (works at today's tiny estate — honestly noted — fails at client scale); fine-tuned judge (stale, uncitable, per-tenant retraining unaffordable). Commits us to: index maintenance, clause-addressable schema, tenant-isolation tests.

## ADR 4: The Risk & Guardrail Decision

**Most material risks:** (1) Control/Governance — who guards the guard: the Sentinel is an agent empowered to halt operations; compromised, it is an ungoverned single point of control. (2) Security — prompt injection in action payloads attacks the referee; one success converts a breach into an allow.

**Decision.** The Sentinel is governed by the instrument it enforces: the Founder & CTO is the named accountability owner in the Sentinel's own FIELD manifest. Structural verdicts are deterministic (no injection surface); the semantic path fails to escalate, never silent-allow or silent-block; the Sentinel cannot modify manifests or its own policy (read-only grounding, separation of duties); one config flag reverts the estate to log-only — who stops the stopper, answered.

- *Guardrail:* every semantic judgment passes an injection screen and a confidence floor; screen trip, below-floor verdict, or structural/semantic disagreement auto-escalates to the named owner; every block and escalation is ledgered.
- *Alternatives rejected:* human review of everything (destroys throughput; impossible solo); unguarded judge (one injection defeats the promise). *Residual risk, stated:* a novel injection that passes the screen with a confident wrong verdict ships a bad allow — mitigated, not eliminated, by log-only burn-in for new agent types, an evolving injection corpus, and ledger review cadence.

## Economics note (provisional until PoC telemetry)

Cost per governed action = structural (≈ 0) + *s* × judgment tokens, with *s* ≈ 15% and ≈ 1,700 tokens per judgment (provisional). Dogfood estate (~300 actions/mo): under a dollar of monthly inference. Modelled 50-agent estate (~300K actions/mo): hundreds to low thousands monthly, linear in actions and *s*. Spike caps: the Sentinel's own manifest spend limit (throttle to structural-only + escalate), pinned/switchable judge, weekly *s* report. The ADR 2 metrics double as the economics dashboard: the spend must buy caught violations, not activity.

## Gates (from the roadmap)

PoC → pilot: catch ≥ 95% on seeded suite, ≥ 2 weeks continuous log-only operation on Spin State's own agents, *s* and would-have-blocked measured. Pilot → production (v1.1 release, Q1 2027, ahead of OSFI E-23 May 2027): false-block ≤ 2% over 30 consecutive days, zero escalations unresolved > 48 h, sponsor sign-off.
