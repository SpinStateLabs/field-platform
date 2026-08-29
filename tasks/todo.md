# tasks/todo.md — Force-Field v1.1 build (extending field-platform)

Authoritative design: `docs/adr/` (ADR packs 02 Sentinel, 07 Crosswalk, 10 Gateway).
Build order 1→2→3 (Sentinel first). Safety ordering: log-only first, enforce after
the measured gate. Verify before "done" (tests / captured run / diff).

## System 1 — Conformance Sentinel (delta on the deterministic engine)

- [x] **S1 — Log-only mode + shadow verdicts.** `FIELD_SENTINEL_MODE=log_only|enforce`.
      Served estate defaults to **log_only** (safe-by-default); one env var flips the
      whole estate. In log-only, `/check` returns ALLOW and ledgers the true outcome
      as `conformance.shadow_block` / `shadow_escalate` (carrying the `would_block`
      clause). Demos/CI that showcase enforcement set `enforce`.
      *Done when:* tests prove log-only shadows without blocking + enforce blocks;
      served default is log_only; existing sentinel tests still green.
- [ ] **S2 — Seeded-violation suite + scorecard.** `seeded.py` + `measure.py` +
      `sentinel score`. Metrics with gates: **catch ≥ 95%**, **false-block ≤ 2%**,
      **s ≈ 15%**, would-have-blocked, tokens/judgment. Sourced report artifact.
- [ ] **S3 — Semantic judge (flagged, mockable).** Invoked only when scope is
      ambiguous; fail-to-escalate; injection screen + confidence floor; version-pinned;
      deterministic mock upstream for tests; spend metered to the Sentinel's own
      manifest. Default judge OFF.
- [ ] **S4 — Sentinel self-manifest + tenant-isolation test.** CTO named owner;
      read-only grounding; agent A's check never reads agent B's manifest.

**Gate to v0.2 (enforce as default):** catch ≥ 95% AND false-block ≤ 2% over ≥ 2
weeks log-only on real agents (invoicing, close); s + would-have-blocked reported.

## Systems 2 & 3 — after the Sentinel gate (own plan-mode passes)

- [ ] System 2 — FORCE Gateway delta (sampled hygiene judge, trend alerts, fail-open + capped).
- [ ] System 3 — Compliance Crosswalk delta (gated suggestions, evidence-pack generator, reg-version staleness).
