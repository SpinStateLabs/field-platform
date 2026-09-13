# SPEC — spend-governor

**Purpose:** Meter spend events (cents, tokens, actions) per agent against
manifest-derived caps. Crossing a configurable threshold (default 80%)
creates an escalation in a human queue *before* the cap; reaching the cap
flips state to BLOCK, which the conformance-sentinel enforces.

**Exec owners:** CFO / CTO.

**FIELD letter:** E — Enforcement.

**v0.1 scope**
- SQLite store: caps, spend events, escalation queue.
- Integer-only arithmetic (money = cents); threshold check is
  `spent*100 >= limit*pct` — exact, no floats.
- `SpendCapConfig.from_manifest` maps the manifest's `enforcement.spend_cap`
  (sub-cent limits refused loudly).
- FastAPI: `/caps`, `/spend`, `/status/{agent}`, `/escalations` (+resolve),
  `/health`. Ledger notes best-effort (`spend.recorded`, `spend.escalate`,
  `spend.cap_reached`, `spend.escalation_resolved`).
- At most one OPEN escalation per (agent, kind): checked and inserted in one
  store call, so concurrent threshold crossings open and ledger one.
- Resolve: first resolver wins. 200 for the resolving call and for the same
  human retrying (unchanged row, no second note); 409 with the unchanged row
  for a different human.
- CLI: `governor set-cap | spend | status | escalations | resolve | serve`.
- Adversarial tests: negative spend rejected; integer boundary exactness at
  99% of a $6,000 cap.

**Explicit non-goals (v0.1)**
- No spend interception — metering is self-reported (decorator/gateway wire
  it in later phases).
- No currency conversion; one currency per cap.
- No `per-run` window semantics (mapped to `total`).
- No LLM anywhere.
