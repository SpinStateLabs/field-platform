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

## field-agent SDK — the last mile (client, not authority)

Approved plan-mode pass 2026-08-29. The SDK adds ZERO new power — it makes the
existing services reachable in a few lines; an agent that never calls it is not
governed (cooperative perimeter, stated in every doc).

- [ ] **FA1 — packages/field-agent package.** FieldAgent facade (check/governed/
      ensure_alive/report_usage[_from]), actions.py re-export of sentinel
      governed.py, liveness+usage clients w/ per-request auth_headers,
      errors (HeartbeatUnreachable ⊂ AgentKilled; strict metering),
      bootstrap.register/mint (not re-exported), fieldagent CLI (UTF-8).
      *Done when:* 14-test suite green incl. 8 adversarial cases
      (sentinel-down fail-closed; killed/unknown/unreachable heartbeat halt;
      no-cap refusal; rogue model/burst; secret-estate 401 contrast).
- [ ] **FA2 — CI + IMPLEMENTATION.md wiring.** --no-deps install line +
      conftest-group test entry, both files. *Done when:* full platform suite
      green locally via the documented commands.
- [ ] **FA3 — demo.sh (<60s, enforce mode).** Register→cap→policy→mint→ALLOW→
      usage→rogue→BLOCK→kill-halt→ledger verify. *Done when:* timed run <60s.
- [ ] **FA4 — invoicing agent through the SDK.** Convert integration/demo
      agent + additive run_demo.sh scenes (set-policy, usage, rogue, 6b
      kill-halt); capture PYTHONUTF8=1 run →
      docs/capstone-evidence/field-agent-run.log. *Done when:* all scenes real,
      log committed, escalation-at-96% story intact.
- [ ] **FA5 — docs.** docs/INTEGRATION.md (9 sections, Enforced-vs-Declared
      honesty throughout), README/ARCHITECTURE/ROADMAP/STATE refresh.
      *Done when:* every claim in docs maps to a test or is marked Declared.
