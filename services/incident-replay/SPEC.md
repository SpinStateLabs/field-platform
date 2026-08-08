# SPEC — incident-replay

**Purpose:** Deterministic reconstruction of an incident window for one
agent from the sealed ledger, the registry, and delegation-authority:
who granted authority, what ran, which clause failed — rendered as a
structured post-mortem and RACI-ready markdown.

**Exec owner:** CISO.

**FIELD letter:** L — Ledger.

**v0.1 scope**
- `POST /replay` and `POST /replay/markdown` (agent id + ISO window).
- Ledger `/verify` gate: reports on a broken chain carry an INTEGRITY
  FAILED banner and refuse to present events as trustworthy.
- Authority = delegation grants overlapping the window; timeline = ledger
  events in window; first failure = first BLOCK/ESCALATE; counts per type.
- RACI derived from registry owner, grantor, and a clause-letter → exec map.
- CLI: `replay run | serve`.
- Adversarial test: on-disk trail edit ⇒ FAILED banner.

**Explicit non-goals (v0.1)**
- No LLM narration (a later, clearly-labeled optional layer).
- No cross-agent correlation or root-cause inference.
- No PDF (attestation-reporter owns board-grade rendering, Phase 4).
