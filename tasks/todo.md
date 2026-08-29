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
- [ ] **S2 — Seeded-violation suite + scorecard.** Approved plan-mode pass 2026-08-29
      (`~/.claude/plans/frolicking-riding-bear.md`, adversarially hardened). Honest
      framing on record: gated numbers are near-tautological by construction (exact-match
      engine, self-authored seeds) — they verify plumbing/regressions, not detection
      power; the real gates stay live (2-week burn-in, 30-day false-block). Sub-items:
  - [ ] **S2.0 — S1 test backfill + docs.** Pin log-only+ledger-down shadowed-ALLOW;
        genuine ALLOW in log-only (no `shadowed` key, `conformance.allow` written);
        escalate-shadow negative assertion + payload; `resolve_mode` synonyms + silent
        unrecognized→log_only fallback (also documented in README LIMITS + .env.example).
  - [ ] **S2.1 — routing.py.** `needs_semantic_judgment(action, scopes)` deterministic
        predicate, measurement-only (zero engine change); S3 attaches the judge here.
  - [ ] **S2.2 — seeded.py.** Deterministic hermetic corpus, 100 actions: scope-breach 8
        →D.scope, expired-token 8→D.expired (ttl=1s, minted first, wait ≥2s), revoked 8
        →D.revoked, ledger-unreachable 8→L.unreachable (renamed from missing-ledger-write;
        reachability proxy only — LIMITS line), ambiguous-violating 8→D.scope
        (post_s3_expected ESCALATE), exact-conforming 53→ALLOW, ambiguous-conforming 7
        →semantic gap. Dedicated seed agents/manifests/tokens; fixture version stamped.
  - [ ] **S2.3 — measure.py.** Log-only hard-required (mode check, else abort); catch
        from in-band `context.would_be`; metrics: gated catch (clause+decision matched),
        raw-refusal catch, seeded structural false-block, false-escalate on conforming,
        combined false-block incl. semantic gap (equal prominence), routing-predicate
        coverage (labeled mix-driven; economics *s* = pending live telemetry),
        would-have-blocked, tokens/judgment=0 ("no judge until S3"), expected-vs-actual
        per-seed table. md+json, every number sourced; gates labeled "(proposed)".
  - [ ] **S2.4 — `sentinel score` CLI.** Live URLs; `--out-json/--out-md`;
        `--include-ledger-down` opt-in (ledger seeds excluded + stated otherwise);
        exit 0 pass / 3 gates fail.
  - [ ] **S2.5 — tests** (`test_scorecard.py`): in-process gate test asserting
        **gated catch ≥ 95% AND structural false-block ≤ 2%** on the full 100-seed
        suite (ledger seeds via `stack.ledger_up`); predicate coverage 100% ambiguous /
        0% exact-conforming; report content + corpus determinism. Suite: 20 existing
        + ≥8 new green via `(cd services/conformance-sentinel && python -m pytest -q tests)`.
  - [ ] **S2.6 — artifact + demo.** `score_demo.sh` (ephemeral log-only stack,
        `--include-ledger-down`, <60 s) → committed
        `docs/capstone-evidence/sentinel-scorecard-s2.md` + `.json`; README scorecard
        section + Enforced-vs-Declared row.
  - [ ] **S2-R (raised, decide separately) — shadow-blind reporting.**
        attestation-reporter + compliance-crosswalk count only `conformance.allow|block|
        escalate`; a log-only estate's board pack shows 100% conformance while violations
        shadow-ledger. Fix before any burn-in starts (touches 2 services + tests).
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

- [x] **FA1 — packages/field-agent package.** FieldAgent facade (check/governed/
      ensure_alive/report_usage[_from]/report_spend), actions.py re-export of
      sentinel governed.py, liveness+usage clients w/ per-request auth_headers,
      errors (HeartbeatUnreachable ⊂ AgentKilled; strict metering),
      bootstrap.register/mint (not re-exported), fieldagent CLI (UTF-8).
      *Done:* 17-test suite green incl. 8 adversarial cases
      (sentinel-down fail-closed; killed/unknown/unreachable heartbeat halt;
      no-cap refusal; rogue model/burst; secret-estate 401 contrast).
- [x] **FA2 — CI + IMPLEMENTATION.md wiring.** --no-deps install line +
      conftest-group test entry, both files. *Done:* 209 green locally via the
      documented commands (also un-time-bombed lifecycle/attestation fixtures).
- [x] **FA3 — demo.sh (<60s, enforce mode).** Register→cap→policy→mint→ALLOW→
      usage→rogue→BLOCK→kill-halt→ledger verify. *Done:* 28 s verified, passes
      plain AND with FIELD_SHARED_SECRET set.
- [x] **FA4 — invoicing agent through the SDK.** Converted integration/demo
      agent + additive run_demo.sh scenes (set-policy, usage, rogue, 6b
      kill-halt); real run captured →
      docs/capstone-evidence/field-agent-run.log. *Done:* all scenes real,
      log committed, escalation-at-96% story intact (exit 0, chain intact).
- [x] **FA5 — docs.** docs/INTEGRATION.md (9 sections, Enforced-vs-Declared
      honesty throughout), README/ARCHITECTURE/ROADMAP/IMPLEMENTATION/STATE
      refresh + capstone evidence narrative. *Done:* 2026-08-29.
