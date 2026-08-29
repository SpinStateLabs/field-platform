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
- [x] **S2 — Seeded-violation suite + scorecard.** Approved plan-mode pass 2026-08-29
      (`~/.claude/plans/frolicking-riding-bear.md`, adversarially hardened). Honest
      framing on record: gated numbers are near-tautological by construction (exact-match
      engine, self-authored seeds) — they verify plumbing/regressions, not detection
      power; the real gates stay live (2-week burn-in, 30-day false-block). Sub-items:
  - [x] **S2.0 — S1 test backfill + docs.** Pin log-only+ledger-down shadowed-ALLOW;
        genuine ALLOW in log-only (no `shadowed` key, `conformance.allow` written);
        escalate-shadow negative assertion + payload; `resolve_mode` synonyms + silent
        unrecognized→log_only fallback (also documented in README LIMITS + .env.example).
  - [x] **S2.1 — routing.py.** `needs_semantic_judgment(action, scopes)` deterministic
        predicate, measurement-only (zero engine change); S3 attaches the judge here.
  - [x] **S2.2 — seeded.py.** Deterministic hermetic corpus, 100 actions: scope-breach 8
        →D.scope, expired-token 8→D.expired (ttl=1s, minted first, wait ≥2s), revoked 8
        →D.revoked, ledger-unreachable 8→L.unreachable (renamed from missing-ledger-write;
        reachability proxy only — LIMITS line), ambiguous-violating 8→D.scope
        (post_s3_expected ESCALATE), exact-conforming 53→ALLOW, ambiguous-conforming 7
        →semantic gap. Dedicated seed agents/manifests/tokens; fixture version stamped.
  - [x] **S2.3 — measure.py.** Log-only hard-required (mode check, else abort); catch
        from in-band `context.would_be`; metrics: gated catch (clause+decision matched),
        raw-refusal catch, seeded structural false-block, false-escalate on conforming,
        combined false-block incl. semantic gap (equal prominence), routing-predicate
        coverage (labeled mix-driven; economics *s* = pending live telemetry),
        would-have-blocked, tokens/judgment=0 ("no judge until S3"), expected-vs-actual
        per-seed table. md+json, every number sourced; gates labeled "(proposed)".
  - [x] **S2.4 — `sentinel score` CLI.** Live URLs; `--out-json/--out-md`;
        `--ledger-down-cmd` opt-in (ledger seeds excluded + stated otherwise);
        exit 0 pass / 3 gates fail.
  - [x] **S2.5 — tests** (`test_scorecard.py`): in-process gate test asserting
        **gated catch ≥ 95% AND structural false-block ≤ 2%** on the full 100-seed
        suite (ledger seeds via `stack.ledger_up`); predicate coverage 100% ambiguous /
        0% exact-conforming; report content + corpus determinism. Suite: 20 existing
        + ≥8 new green via `(cd services/conformance-sentinel && python -m pytest -q tests)`.
  - [x] **S2.6 — artifact + demo.** `score_demo.sh` (ephemeral log-only stack,
        `--ledger-down-cmd`) → committed
        `docs/capstone-evidence/sentinel-scorecard-s2.md` + `.json`; README scorecard
        section + Enforced-vs-Declared row. *Measured:* real run 82 s — the <60 s
        target missed (500 localhost HTTP round-trips on Windows loopback);
        relaxed to <2 min and recorded, not silently shaved.
  - [x] **S2-R — shadow-aware reporting (approved + done 2026-08-29).**
        Board pack: shadow_block/shadow_escalate get their own labeled rows ("log-only,
        not enforced") and count in the conformance-rate denominator (rate renamed
        "… incl. shadow"; a log-only estate can no longer read 100% — adversarial test
        stages shadow events → 37.5%). Crosswalk FC-E-03 evidence labels enforced vs
        shadow escalations distinctly. run_demo.sh metric-name consumer updated;
        real integration-demo run green (exit 0, rate 71.4% unchanged in enforce mode
        — shadow terms are 0). Suites: attestation 7/7, crosswalk 10/10.
- [x] **S3 — Semantic judge (flagged, mockable).** Plan-mode pass 2026-08-29
      (auto-approved by user directive; `~/.claude/plans/frolicking-riding-bear.md`).
      Honest framing: mock tests prove CONTROL FLOW (fail-to-escalate, screen, floor,
      throttle, routing) — semantic understanding stays Declared until live golden
      evals. Default OFF = zero behavior change. Judge evaluates EFFECTIVE scope
      (token∩manifest) to preserve narrower-grant-wins. Sub-items:
  - [x] **S3.1 — field-core `D.semantic` clause** (no fixed-CLAUSES consumers; 58/58 green).
  - [x] **S3.2 — judge.py.** Pinned JUDGE_MODEL_DEFAULT (env override recorded in every
        verdict); JudgeVerdict; deterministic injection_screen (pattern list + length
        cap); MockJudgeClient (records calls); AnthropicJudgeClient (httpx, key from
        env only, strict-JSON rubric, action marked DATA; errors raise);
        FIELD_SENTINEL_JUDGE=off|mock|anthropic (default off, unrecognized→off);
        FIELD_JUDGE_CONFIDENCE_FLOOR default 0.8.
  - [x] **S3.3 — engine step-5 judge path.** Screen→spend gate (sentinel's own cap via
        governor /status; no cap/BLOCK/unreachable ⇒ ESCALATE D.semantic structural-only
        throttle)→judge→strict metering (governor /usage; failure ⇒ ESCALATE)→verdict
        (conforming≥floor ⇒ remaining checks still run; violating≥floor ⇒ BLOCK D.scope
        w/ sanitized rationale; else ESCALATE D.semantic); sentinel.judge ledger
        telemetry; all through _verdict (log-only shadows apply). /health reports judge.
  - [x] **S3.4 — tests** (*done:* 20 new, sentinel 52/52; existing 32 unmodified
        except one stale honesty-string assertion updated):
        7 adversarial fail-to-escalate paths all ⇒ ESCALATE D.semantic never ALLOW;
        golden set via mock rules from seed labels: AC 7/7 ALLOW, AV 8/8 BLOCK D.scope,
        SB 8/8 BLOCK with ZERO judge calls; narrower-grant intersection; log-only
        shadow of judge BLOCK; no-bypass of remaining checks.
  - [x] **S3.5 — measure/cli honesty refresh + artifact regen.** *Done:* real
        score_demo re-run 89 s, gates PASS unchanged (served-estate proof the
        judge-off delta is behavior-neutral); scorecard refuses judge-on runs. tokens/judgment source
        is judge-state-aware (stale "no judge until S3" replaced); score_demo re-run,
        artifact recommitted. README judge section + Enforced-vs-Declared + LIMITS;
        .env.example.
- [x] **S4 — Sentinel self-manifest + tenant-isolation test.** Plan-mode pass
      2026-08-29 (auto-approved by user directive). Who guards the guard, as tested
      properties — every claim Enforced (test) or labeled Declared. Sub-items:
  - [x] **S4.1 — self_manifest.yaml** (package data, committed): principal
        "Founder & CTO, Spin State Labs"; read-only-grounding scope (read/evaluate/
        append/invoke verbs only); spend_cap USD 5/daily = the S3 judge budget
        (manifest is the budget's source of authority via existing
        `governor set-cap --from-manifest`); validates via field-core.
  - [x] **S4.2 — self_manifest.py + `sentinel self-manifest` CLI** (*done:* real
        run exit 0, owner/budget/scope printed) (validate +
        print; exit 1 if invalid — a governance artifact failing validation is loud).
  - [x] **S4.3 — tests (*done:* 7 new, suite 59/59, existing 52 unmodified):** manifest
        validates + CTO + cap + verb-restricted scope; manifest-derived cap →
        mock-judged call ALLOWED and metered (completes S3 spend story); tenant
        isolation structural (resolver spy: check(A) reads ONLY A's manifest_ref;
        B's grant never leaks) + judge path (mock scope ⊆ A's manifest); read-only
        API surface (no PUT/PATCH/DELETE; POST only /check); manifest bytes
        identical after a full check battery.
  - [x] **S4.4 — README self-governance section** (Enforced-vs-Declared rows;
        LIMITS: OS-level manifest immutability is a deployment concern — mount
        read-only) + STATE/todo/memory + commit/push both remotes.

**Gate to v0.2 (enforce as default):** catch ≥ 95% AND false-block ≤ 2% over ≥ 2
weeks log-only on real agents (invoicing, close); s + would-have-blocked reported.

## Systems 2 & 3 — after the Sentinel gate (own plan-mode passes)

- [x] **System 2 — FORCE Gateway delta (ADR Pack 10).** Plan-mode pass 2026-08-29
      (auto-approved by user directive). Observer that fails OPEN — the mirror image
      of the Sentinel: per-item judge noise acceptable (aggregates/trends), faults
      bypass rather than block, gaps visible in coverage, never silent. Sub-items:
  - [x] **G1 — hygiene_judge.py.** Pinned cheap-class model
        (claude-haiku-4-5-20251001, env override), RUBRIC_VERSION=hygiene-v1,
        FORCE_HYGIENE_JUDGE=off|mock|anthropic (default off, unrecognized→off);
        deterministic 1-in-N sampling (FORCE_GATEWAY_SAMPLE_EVERY, default 10, 0=off).
  - [x] **G2 — drift.py trend alerts.** Count-based windows (5), baseline = first 2
        windows, band ±0.15; alert ONLY on two consecutive out-of-band windows,
        re-arm after recovery; model/rubric change resets baseline;
        gateway.drift_alert ledger event.
  - [x] **G3 — fail-open + capped (api.py).** Full bypass on instrumentation fault
        or overhead > FORCE_GATEWAY_LATENCY_BUDGET_MS (250): forward ORIGINAL body
        uninstrumented for cooldown (10), gateway.bypass ledgered on entry; judge
        bypass on no-cap/BLOCK/governor-down (structural telemetry continues);
        /telemetry coverage counters — never silent; /health judge+bypass.
  - [x] **G4 — gateway self-manifest** (*done:* real `forcegw self-manifest` run exit 0) (S4 pattern): CTO owner, observer-verb scope,
        USD 5/daily judge budget via `governor set-cap force-gateway --from-manifest`;
        `forcegw self-manifest` CLI.
  - [x] **G5 — tests (*done:* 20 new, suite 33/33, existing 13 unmodified)** + README
        (Enforced-vs-Declared; LIMITS: session-scoped in-memory state until the
        telemetry-persistence backlog item; judge quality Declared pending quarterly
        human calibration) + .env.example + STATE/todo/memory + push both remotes.
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
