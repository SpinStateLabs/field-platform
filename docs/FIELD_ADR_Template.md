# FIELD ADR Template

**Spin State Labs · Force-Field collateral · v1.0 (2026-08-29) · MIT**

An Architecture Decision Record captures one significant technical decision — the context, the decision in one sentence, the alternatives considered, and what the choice costs or commits you to — so that six months from now, "why did we build it this way?" is answered by a document, not a memory. The accounting analogue: a signed accounting-policy memo. Write one package (four ADRs) per AI system. Commit to `docs/adr/` in the system's repo. When a decision changes, append an amendment with a date — never rewrite history.

---

# ADR Package — [System Name] (Initiative #N)

**[Org] · Status: design record | in build | shipped · [date] · [license]**
System: [one sentence — what it does, stated as a system, not a category]. Buyer: [executive role]. Timing driver: [the external clock, if any].

## ADR 1: The Model Decision

**Context.** [What task is the system actually performing — classification, generation, retrieval, scoring? Then the discipline question: what is the *simplest* model class that could plausibly do this — including "no model at all" — and what specifically makes it sufficient or insufficient?]

**Decision.** [One sentence: a specific model class or sourcing path, never "we will use AI."]

- *Bias–variance:* [Does the choice favour a simpler, lower-variance, auditable approach, or a flexible, higher-variance one — and why is that the right side of the trade for the decision this system's output feeds?]
- *Vendor exposure:* [Who supplies the capability; exposure to price, drift, deprecation; how you switch.]

**Alternatives Considered**

| Path | Why Considered / Rejected | What It Would Cost or Expose Us To |
|---|---|---|
| [Alternative 1] | | |
| [Alternative 2] | | |
| **Chosen path** | | [What it commits you to maintaining] |

## ADR 2: The Decision & Measurement Design

**Context.** [What the system outputs, and — name the action, not the number — what real-world action that output triggers, and who or what takes it.]

**Decision.**

- *False positive, in this context, and its cost:* [ ]
- *False negative, in this context, and its cost:* [ ]
- *Which mistake you optimize against, and the resulting threshold or policy:* [A business judgment, stated as one.]
- *The metric you track, and why it is not raw accuracy:* [Accuracy hides class imbalance and punishes honest "unknown"s — name the one or two numbers that actually indicate the outcome.]

**Alternatives Considered** — [same 3-row table; use the third row to state the gap you accept between what the model optimizes, what you evaluate, and what deployment actually cares about.]

## ADR 3: The Data & Grounding Decision

**Context.** [What the system must know that no foundation model knows — your policies, your manifests, your catalogue — and where that knowledge lives today, in what shape.]

**Decision.** [Retrieval, fine-tuning, hybrid — or, legitimately, none: a small, stable, versioned rubric needs configuration management, not RAG. Then: who keeps it current, and does the grounding respect who is allowed to see what. If retrieval: specify the pipeline — chunking that follows document structure, index and isolation model, query-time search and re-ranking, prompt assembly — and whether typical inputs are short or long, since that shapes the economics.]

**Alternatives Considered** — [same table.]

## ADR 4: The Risk & Guardrail Decision

**Context.** [Of the six categories — performance, security, control/governance, societal, economic, ethical — name the TWO most material for this system, this data, this user population, and say why the other four rank lower *here*. They still matter; they are not where the gates sit.]

**Decision.** [If the system takes actions: who is accountable when it deviates from policy (a named role, in the system's own FIELD manifest), and what stops the action before it lands. If generation-only: how a confidently wrong answer is caught before a human relies on it, and what the safe fallback is.]

| Guardrail (one sentence) | [The check that runs before anything ships, and where blocks/escalations are logged.] |
|---|---|
| Trigger, action, accountable role | [Trigger conditions · what fires · named role, not a function.] |

**Alternatives Considered** — [same table; the third row names the residual risk that remains even with the chosen control. A risk section that dismisses every concern is not credible.]

## Economics note

[Cost per interaction as a formula with stated assumptions · expected volume · run-rate order of magnitude · what makes it spike and what caps it. Tie the spend to the ADR 2 metric: the same number that proves the system works is the number that proves the spend buys outcome, not activity.]
