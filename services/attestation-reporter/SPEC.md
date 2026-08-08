# SPEC — attestation-reporter

**Purpose:** Render the governance board pack from live services in one
command: HTML + JSON (+ best-effort PDF), with every figure carrying the
literal query it came from. Ledger integrity leads the pack because every
other number stands on it.

**Exec owner:** CEO / board.

**FIELD letters:** all — this is the executive view over the platform.

**v0.1 scope**
- `attest render` CLI → `board-pack.{json,html,pdf?}`.
- `Metric` model enforcing: value ⇒ source_query; unavailable ⇒ no value
  (no fabricated zeros).
- Sections: integrity, agents, conformance (rate + raw counts with printed
  formula), enforcement, delegation (expiry window computed client-side,
  formula noted), federation & lifecycle.
- PDF via headless Edge/Chrome when present (OQ-3 resolved as best-effort;
  HTML canonical).
- Adversarial tests: governor-down ⇒ unavailable; tampered chain ⇒ BROKEN
  leads the pack.

**Explicit non-goals (v0.1)**
- No time series / warehousing (archive the packs).
- No scheduling (pair with lifecycle-manager's scheduler).
- No LLM commentary — the pack is numbers with sources, full stop.
