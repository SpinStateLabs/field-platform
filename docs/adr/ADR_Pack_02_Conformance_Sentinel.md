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

*Reviewer notes, added 2026-10-29 (the text below is unchanged): (1) the block breakdown 1 + 57 + 2 + 2 in the Measured PoC paragraph sums to 62, not the 63 blocks stated (73 + 63 = 136 holds); I do not know which figure is correct; the live ledger is not in the repository. (2) Two sets of gate numbers exist for the same milestone: the ratified gates below (catch ≥ 97.8%, false-block < 1.6%) and the seeded scorecard's own gates in `docs/capstone-evidence/sentinel-scorecard-s2.json` (`meta.gates`: catch ≥ 95%, false-block ≤ 2%); on the seeded structural figures the scorecard clears both numerically (gated catch 40/40, structural false-block 0/53), but the same scorecard reports a combined false-block rate of about 11.7% (the 7 ambiguous conforming seeds that would be blocked with the semantic judge off), which is above both false-block limits, so "clears both" holds for the structural rate only. I do not know which set governs the pilot decision; that is a ruling for the owner, not something the repository settles.*

PoC → pilot gates (ratified 2026-08-29): catch ≥ 97.8% on seeded suite; false-block < 1.6% live. Pilot → production (FIELD v1.1 general release, **November 2026**, ahead of OSFI E-23 May 2027): false-block < 1.6% over 30 consecutive days, zero escalations unresolved > 48 h, sponsor sign-off.

**Measured PoC (2026-08-08 → 08-29, hash-chain-verified):** 136 live verdicts — 73 allow / 63 block, 0 false blocks; blocks = 1 out-of-scope real-order attempt, 57 expired-authority (fail-closed 9.5 days), 2 unregistered-agent, 2 missing-manifest. *s* = 0%; $0.00 LLM. Kill drill: 20.45 ms kill, 22.41 ms heartbeat, restored. Duration condition met (16 unbroken days).
**Function battery (2026-08-29): 52/52 PASS** — all enforcement clauses, judge rules (injection screen before judge; judge pass bypasses nothing), log-only shadow mode, self-governance checks, fail-closed on sentinel/ledger-unreachable, hash chain verified.
**Seeded scorecard S2 (2026-08-29, log-only, fixtures s2-fixtures-v1):** gated catch 40/40 = 100% (clears ≥ 97.8%); seeded structural false-block 0/53 = 0% (clears < 1.6%). Scorecard's own caveat: structural seeds verify plumbing, not detection power; 7/7 paraphrased-conforming probes would-block today — the semantic judge's job, measured by the pilot's live gate.
**Client-engagement onboarding (2026-09-08):** ssl-invoicing-agent and ssl-timekeeping-agent manifested and governed in enforce mode; skill-agent perimeter honestly documented as cooperative (see `agents/README.md` enforced-vs-declared table).

> **Code and ADR compared (added 2026-10-30, card C-545, reviewer C-529; the text above is unchanged).** Checked against `services/conformance-sentinel/src/conformance_sentinel` on the main branch; each line cites what a reader can re-read.
> 1. **ADR 3 (retrieval, per-tenant indexes, re-ranking, re-index on merge) is not built.** A search of the service source and its tests for retrieval, index, chunk, re-rank, embedding and notification code finds none. What exists is a manifest lookup per check: the engine reads the agent record and resolves that agent's manifest by `manifest_ref` (`engine.py:485`, `engine.py:509`), and two tests pin that agent A's check never reads agent B's manifest (`tests/test_self_manifest.py:93`, `:123`). That is per-agent isolation, not the per-tenant indexes of ADR 3.
> 2. **No owner notification exists.** A BLOCK or ESCALATE is a verdict plus a ledger record (`engine.py:242-262`); nothing in the service routes it to a named owner.
> 3. **A structural miss followed by a judge affirmation is not escalated.** When the exact scope check fails and the semantic judge affirms conformance, `judged_conforming` is set and "remaining checks still run" (`engine.py:550-557`); the verdict can then be ALLOW (`engine.py:641`). There is no structural/semantic disagreement escalation.
> 4. **"Block halts pre-execution" holds for a cooperating enforcement point in enforce mode only.** The service returns a verdict; the caller must honour it. In log-only mode every `/check` returns ALLOW and a would-block is shadow-recorded (`mode.py:3-5`, `engine.py:193-196`). A mistyped `FIELD_SENTINEL_MODE` refuses to start instead of meaning log-only (`mode.py:34-47`, C-169).
> 5. **"Every block and escalation is ledgered" is best-effort.** BLOCK and ESCALATE records are written best-effort ("a block that cannot be recorded is still a block", `engine.py:242-244`); in enforce mode an ALLOW whose record the ledger refuses becomes BLOCK `L.unreachable` (`engine.py:264-277`).
> 6. **Owner-reported figures with no artifact in this repository:** the 136 live verdicts and their breakdown, and the kill-drill timings (Measured PoC paragraph above), and the cost figures ($0.34, about 195 verdicts a month, *s* of about 15%, about 1,700 tokens; Economics note above). The seeded scorecard reports a routing coverage of 0.15 (`docs/capstone-evidence/sentinel-scorecard-s2.json`, `scorecard.routing_coverage`), which may be where 15% comes from; I do not know. The earlier reviewer note about the 62 versus 63 blocks still stands.
