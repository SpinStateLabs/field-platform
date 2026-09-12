# ADR Package — Conformance Sentinel (Initiative #2 · FIELD v1.1)

**Spin State Labs · Force-Field platform · Status: design record, build shipped (deterministic core) · updated 2026-09-12 · MIT**
System: an agent that continuously audits deployed AI agents against their FIELD governance manifests and blocks non-conforming actions — scope breaches, expired authority, missing ledger writes — at the policy-enforcement point, before they execute. Buyer: CISO. This system is the public "enforcement in v1.1" commitment on spinstatelabs.ca/field.
*Authoritative design record for `services/conformance-sentinel`; supersedes the build brief's System 1 section. The graded UWaterloo Deliverable B is the grading copy of this package.*

## ADR 1: The Model Decision

**Decision.** A deterministic policy engine is the primary evaluator; a commercial LLM is invoked by API only for semantic scope judgments the rules cannot resolve — no training, no self-hosting.

- *Simplest class considered:* no model at all — deterministic evaluation of structured manifest fields (scope lists, authority expiry, spend caps, required ledger writes). Sufficient for structural conformance; insufficient for natural-language scopes.
- *Bias–variance:* enforcement demands low-variance, auditable behaviour; the high-variance LLM judgment is confined to a narrow, escalate-on-uncertainty role. Flexibility traded for reproducibility, deliberately.
- *Vendor exposure:* judge is stateless and prompt-defined; pinned versions, provider abstraction, golden-set regression on swap. The deterministic engine has no vendor dependency.
- *Alternatives rejected:* LLM-judges-everything (~100× cost, non-reproducible, no audit trail); rules-only (semantic breaches undetected). Chosen path commits us to: manifest schema versioning, engine maintenance, a golden test set, swap regression.

## ADR 2: The Decision & Measurement Design

**Decision.** Output = allow / block / escalate per action, each citing its manifest clause. Block halts pre-execution and notifies the owner; escalate pauses for a human.

- *False block* (conforming action halted): operational delay + eroded trust → owners route around governance. *False allow* (breach executes): the incident the product exists to prevent; existential for credibility.
- *Policy — asymmetric by tier:* structural violations hard-block (near-zero false blocks by construction; optimize against false negatives); semantic judgments fail to escalate (optimize against false positives under uncertainty); allow only on affirmative conformance.
- *Metrics:* seeded-violation catch rate (gate ≥ 97.8%) + live false-block rate (gate < 1.6%); ratified by the accountable owner 2026-08-29. Raw accuracy is decorative here — conformant actions dominate, so always-allow scores >99%.
- *Accepted gap:* judge optimizes a general objective; eval uses seeded violations; deployment cares about client-specific costs. Drift among the three is monitored by ledger review cadence and periodic re-seeding.

## ADR 3: The Data & Grounding Decision

**Decision.** Retrieval over the estate's manifests and referenced policies; no fine-tuning.

- *Why:* manifests are per-agent, per-client, and change on redeploy — wrong to freeze into weights; verdicts must cite the exact current clause (auditor requirement); updates are re-index-on-merge.
- *Pipeline:* clause-level chunking (structure-following) → one index per tenant (isolation is a tested property) → action descriptor + agent identity retrieves candidate clauses, re-ranked by action type → short prompt → verdict with citation.
- *Access:* per-tenant indexes; Sentinel reads under read-only authority; manifest owner keeps content current via version control.
- *Alternatives rejected:* long-context stuffing (fails at client scale); fine-tuned judge (stale, uncitable, per-tenant retraining unaffordable). Commits us to: index maintenance, clause-addressable schema, tenant-isolation tests.

## ADR 4: The Risk & Guardrail Decision

**Most material risks:** (1) Control/Governance — who guards the guard: the Sentinel is an agent empowered to halt operations; compromised, it is an ungoverned single point of control. (2) Security — prompt injection in action payloads attacks the referee; one success converts a breach into an allow.

**Decision.** The Sentinel is governed by the instrument it enforces: the Founder & CTO is the named accountability owner in the Sentinel's own FIELD manifest (verified by battery case 6.3). Structural verdicts are deterministic (no injection surface); the semantic path fails to escalate, never silent-allow or silent-block; the Sentinel cannot modify manifests or its own policy (read-only grounding — battery 6.2; no mutating routes — battery 6.4); one config flag reverts the estate to log-only.

- *Guardrail:* every semantic judgment passes an injection screen and a confidence floor (screen trips before any judge call — battery 3.5); screen trip, below-floor verdict, or structural/semantic disagreement auto-escalates to the named owner; every block and escalation is ledgered. Sentinel-unreachable and ledger-unreachable both fail closed (battery 2.4, 8.1).
- *Alternatives rejected:* human review of everything (destroys throughput); unguarded judge (one injection defeats the promise). *Residual risk, stated:* a novel injection that passes the screen with a confident wrong verdict ships a bad allow — mitigated, not eliminated, by log-only burn-in for new agent types, an evolving injection corpus, and ledger review cadence.

## Economics note (measured)

Cost per governed action = structural (≈ 0) + *s* × judgment tokens. Measured PoC: *s* = 0%, $0.00 LLM, $0.34 ledgered over 21 days (~195 verdicts/month). Client-scale model: *s* ≈ 15%, ~1,700 tokens/judgment. Spike caps: the Sentinel's own manifest spend limit, pinned/switchable judge, weekly *s* report. The ADR 2 metrics double as the economics dashboard.

## Gates and measured evidence

PoC → pilot gates (ratified 2026-08-29): catch ≥ 97.8% on seeded suite; false-block < 1.6% live. Pilot → production (FIELD v1.1 general release, **November 2026**, ahead of OSFI E-23 May 2027): false-block < 1.6% over 30 consecutive days, zero escalations unresolved > 48 h, sponsor sign-off.

**Measured PoC (2026-08-08 → 08-29, hash-chain-verified):** 136 live verdicts — 73 allow / 63 block, 0 false blocks; blocks = 1 out-of-scope real-order attempt, 57 expired-authority (fail-closed 9.5 days), 2 unregistered-agent, 2 missing-manifest. *s* = 0%; $0.00 LLM. Kill drill: 20.45 ms kill, 22.41 ms heartbeat, restored. Duration condition met (16 unbroken days).
**Function battery (2026-08-29): 52/52 PASS** — all enforcement clauses, judge rules (injection screen before judge; judge pass bypasses nothing), log-only shadow mode, self-governance checks, fail-closed on sentinel/ledger-unreachable, hash chain verified.
**Seeded scorecard S2 (2026-08-29, log-only, fixtures s2-fixtures-v1):** gated catch 40/40 = 100% (clears ≥ 97.8%); seeded structural false-block 0/53 = 0% (clears < 1.6%). Scorecard's own caveat: structural seeds verify plumbing, not detection power; 7/7 paraphrased-conforming probes would-block today — the semantic judge's job, measured by the pilot's live gate.
**Client-engagement onboarding (2026-09-08):** ssl-invoicing-agent and ssl-timekeeping-agent manifested and governed in enforce mode; skill-agent perimeter honestly documented as cooperative (see `agents/README.md` enforced-vs-declared table).
