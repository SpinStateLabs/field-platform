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
- [x] **System 3 — Compliance Crosswalk delta (ADR Pack 07).** Plan-mode pass
      2026-08-29 (auto-approved; parallel 3-agent build on disjoint modules per user
      request — all three returned green first pass). Everything bends against ONE
      error: a signed false assurance.
  - [x] **C1 — suggestions.py (gated).** CROSSWALK_SUGGEST=off|mock|anthropic default
        off; precision floor 0.8: below-floor/error ⇒ "unmapped — review required",
        NEVER a candidate; disclaimer on every entry; authored CONTROLS matrix stays
        sole source of truth (immutability test).
  - [x] **C2 — evidence_pack.py.** Three-part citations (clause · control ·
        reg reference + retrieved date); NO pack without a named signer; "Signature
        is the action — this system never asserts compliance"; stale flags hard-block
        generation (no override); pending-text/pending-purchase rendered honestly.
  - [x] **C3 — staleness.py (reg-version).** CORPUS_VERSION pinned; StaleStore at
        $FIELD_DATA_DIR; mark/clear (named reviewer, logged history); stale window
        length reported; affected_controls listed. Detection is operator-fed in v1
        (fetch-tooling limits on EUR-Lex are on record) — Declared in LIMITS.
  - [x] **C4 — self-manifest + CLI/api wiring + docs.** S4 pattern (CTO owner, USD
        5/daily suggestion budget); `crosswalk suggest|pack|regwatch|self-manifest`;
        GET /staleness; README Enforced-vs-Declared + LIMITS; .env.example.
  - [x] **C5 — gates.** *Done:* suite 42/42 (10 existing unmodified + 32 new);
        real CLI sequence captured (self-manifest exit 0; set-stale eu-ai-act →
        pack BLOCKED exit 3 naming affected controls, "there is no override" →
        clear --reviewed-by → pack exit 0 with verbatim never-asserts-compliance
        disclaimer + corpus-2026-08-08 + 36 control-citation rows); pushed both.

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

## v1.2 — 12-system closure (2026-09)

Spec: `../tasks/claude-code-prompt-v1.2-12-system-closure.md` (Don, 2026-09-12)
+ Don's 2026-09-12 slide "DECLARED, NOT YET ENFORCED" (Phase F). Ground
truth: `../tasks/audit-v2-12-systems-vs-production-build-2026-09-12.md`
(audited @ ad7a79c). Plan grounded against main **1727de0** by 13 read-only
code readers, then adversarially reviewed by 5 lenses + critic (61 findings
folded in; none reverses a decision). The decisions table is fixed; below
says HOW and names blockers. Order A → B → C → D → F → E, one phase at a
time; after each phase summary: STOP for Don. Every CLOSE item = code +
adversarial test + README Enforced-vs-Declared row + LIMITS + SPEC in ONE
commit; REWORD = wording only. Per-service DoD unchanged (README
"Development"): every touched `demo.sh` exits 0 in < 60 s (< 2 min for
stacks > 5 services), wall time pasted next to the `run_demo.sh` tail at
each gate. Build pattern (spec rule 6): each phase is built by parallel
subagents, one module each, with the file ownership stated in the phase
header; an adversarial review agent signs off before each gate. Commits per
item with conventional messages (`feat(<service>): …`, `docs(state): …`,
`test(<service>): …`). `python -m pytest` in `~/.venvs/field-platform`;
UTF-8 stdout; `--out` flags; LF `.sh`; 1 s SQLite settle; frozen clocks via
`now=`/`clock=` seams, never sleeps. New clause ids in field-core with tests.
No deploy: compose/fly/CI edits are CI-verified only; both estates run
pre-v1.2 images until Don redeploys, so every "Enforced" below is test/CI-
proven and every estate status is Declared until then (Phase E carries that
line into the one-liners).

### Pre-flight
- [x] **P0 — Premise corrections (verified by readers and reviewers).** (1)
      Both images omit lifecycle-manager and attestation-reporter
      (`integration/demo/Dockerfile:10-22`, `integration/fly/Dockerfile:
      23-35`; STATE.md:80-81 "eleven packages" is wrong) — A0 adds them. (2)
      `E.rate_limit` already exists (`field_core/conformance.py:32`) — D1
      cites and pins it; only `D.grantor` is new. (3) `FORCE_GATEWAY_URL`
      exists nowhere; `FIELD_GATEWAY_URL` is the CLI target (`force_gateway/
      cli.py:24`) — D2 introduces the former, keeps both. (4) The only
      manifest resolver is the sentinel's `ManifestResolver`
      (`conformance_sentinel/engine.py:109-144`); B1, B3, C2, C3 need it — it
      moves to field-core FIRST (B0). (5) The per-action throttle has no data
      source today (spend rows carry no action name) — D1 adds one. (6)
      Every manifest the kill-switch could resolve (shipped ssl-*.yaml:43/47,
      demo + plugin manifests, three self-manifests, sentinel + field-agent
      conftests) points back at the kill-switch's own `/kill/{agent}`; other
      fixtures (federation `borealis.example/kill`, parity `method: file`)
      never reach it — B3 needs a self-call guard. (7) `def test_` = 298
      today (STATE/ROADMAP say 209) — E2 cites `pytest --collect-only`
      counts. (8) The verbatim v2 one-liners exist only as phrases quoted in
      the audit — see E1. (9) The "probe /health from a separate call" rule
      is in the parent `../tasks/lessons.md`, not the in-repo one — A-gate
      adds it. (10) compose forwards NO host env into containers (`&env` is
      a fixed map; only `${VAR:-}` references do; the gb10 override forwards
      `ANTHROPIC_API_KEY` to the sentinel only) — every "Don can enable it
      from the estate .env" variable below gets a passthrough line in A0.
      *Done when:* Don replies "P0 acknowledged" with the approval, and
      STATE.md "Current phase" carries these ten corrections as a dated
      bullet list.
- [x] **P1 — Repo hygiene and branch strategy.** Don merges the pending
      `claude/state-field-gate-1-1-0` (df774fe, STATE.md +84/−1) BEFORE P2 —
      P2, A4 and every phase gate write STATE.md on `main`; never two
      competing STATE.md heads. The uncommitted `docs/adr/ADR_Pack_02_
      Conformance_Sentinel.md` edit (+20/−15) is committed by Don as
      `docs(adr): …` or discarded before the first v1.2 commit; it never
      rides inside an item commit. Commits per item on `main` (as every prior
      phase); push at each phase gate (CI runs on push; `gh` is not installed
      on rog-command). *Done when:* `git status` clean on main containing
      df774fe; Don approves the strategy and this plan.
- [x] **P2 — Estate caveat on record.** GB10 (636e4bb) and Fly (e07cd5b) run
      pre-v1.2 code. Running "needs redeploy / decision by Don" list, grown
      at each gate: fly.toml memory (A4); registry SQLite migration —
      forward-only, an older image can read but not register; back up
      `/data/registry` first (B4); `--mock` removal ⇒ GB10 keyless 502 on
      `/v1/messages` until `ANTHROPIC_API_KEY` is set in the GB10 .env (now
      forwarded) (D2); `FIELD_DOA_ROSTER` / `FIELD_LIFECYCLE_ROSTER` files on
      `/data` + env (B1/A1); `FIELD_KILL_ENDPOINT_ALLOWLIST` (B3);
      `FIELD_LEDGER_RETENTION_DAYS ≥ 2555`, archive dir under `/data`,
      `FIELD_LEDGER_ANCHOR_KEY` custody (C2); crosswalk daily egress network
      policy (D4); `FORCE_GATEWAY_URL` estate-wide (D2e); `FORCE_GATEWAY_
      ENFORCE`, ledger/attest signing keys (F); plugin 0.1.2 bump owed since
      1727de0. *Done when:* the caveat line + this list are in STATE.md
      "Current phase" before A starts.

### Phase A — serve the three CLI-only systems (7, 11, 12)
File ownership: subagent 1 = A0 wiring (compose, gb10, both Caddyfiles,
entrypoint, Dockerfiles, ci.yml, .env.example, IMPLEMENTATION §3, READMEs);
subagent 2 = A1 lifecycle; subagent 3 = A2 attest; subagent 4 = A3
crosswalk. Only subagent 1 touches shared wiring files.
- [x] **A0 — Images, deps, wiring, passthroughs.** Add `./services/
      lifecycle-manager` and `./services/attestation-reporter` to both
      Dockerfiles (fix the "KEEP IN SYNC"/"eleven packages" comments; order
      after spend-governor for B4); move `fastapi`/`uvicorn` into
      `dependencies` of both pyprojects (crosswalk's pyproject is the
      pattern). compose `x-service` `&env`: add `FIELD_LIFECYCLE_URL`
      (http://lifecycle:8012), `FIELD_ATTEST_URL` (http://attest:8013),
      `FIELD_CROSSWALK_URL` (http://crosswalk:8008), the already-missing
      `FIELD_GATEWAY_URL` (http://forcegw:8009) and `FIELD_FEDERATION_URL`
      (http://fedbroker:8010), and the passthrough lines `FIELD_DOA_ROSTER:
      ${FIELD_DOA_ROSTER:-}`, `FIELD_LIFECYCLE_ROSTER: ${…:-}`,
      `FIELD_LIFECYCLE_EVERY: ${…:-86400}`, `FIELD_CROSSWALK_EVERY:
      ${…:-86400}`, `FIELD_KILL_ENDPOINT_ALLOWLIST: ${…:-}`,
      `FIELD_LEDGER_RETENTION_DAYS: ${…:-2555}`, `FIELD_MANIFEST_DIR:
      ${…:-/data/manifests}`, `FIELD_SHARED_SECRET: ${…:-}`; forcegw block:
      `FORCE_GATEWAY_MOCK: ${…:-}` and `ANTHROPIC_API_KEY: ${…:-}` (blank
      by default; enabled from the estate .env with no compose edit at
      deploy time); three service blocks (`<<: *svc`, `restart:
      unless-stopped`, depends_on); `proxy` depends_on extended; gb10
      override header prefix list. Both Caddyfiles: `handle_path
      /lifecycle/*`, `/attest/*`, `/crosswalk/*` before the console
      catch-all; delete the "stays uncomposed" comments. `entrypoint.sh`:
      the same exports (loopback URLs; `FIELD_LIFECYCLE_EVERY`/
      `FIELD_CROSSWALK_EVERY` default 86400 so Fly ticks too) + three serve
      lines; "ten-service" → thirteen. `.env.example`, `docs/IMPLEMENTATION.md`
      §3 table + prefix list + boot order, `integration/{demo,fly}/README.md`,
      `docs/ARCHITECTURE.md` labels. ci.yml: both health loops → 12 prefixes
      + console; the fixed `sleep 20` becomes a bounded per-prefix retry (13
      cold uvicorn starts on one vCPU; no other CI semantics change). *Done
      when:* `docker compose config` renders every default and none is set
      to a value in CI; Caddyfiles and fly.toml parse; both smoke jobs
      health-check 12 prefixes + console and pass on the pushed commit; both
      images build with lifecycle-manager listed after spend-governor.
- [x] **A1 — lifecycle serve.** New `lifecycle_manager/api.py`
      `create_app(registry=None, delegation=None, ledger=None,
      killswitch=None, roster_path=None, every=None)` + `install_authn`
      (`/health` open). `POST /sweep` body `SweepRequest(extra='forbid')`:
      `roster_csv: str|None` (JSON string field — keeps the forbid guard),
      `expiry_days`, `reattest_days`, `operator`, `auto_kill_orphans: bool =
      False`; the kill-switch client is constructed ONLY when the body flag
      is literally true (mirrors cli.py:54-60) — the scheduler path can never
      arm it and no env var can either (grep-guard test: api.py and the
      scheduler read no variable containing `AUTO_KILL`). Roster: body
      `roster_csv` else the file at `FIELD_LIFECYCLE_ROSTER`; neither ⇒ 503
      "no roster" (never a silent empty roster, which would orphan every
      agent). `GET /findings` = last `SweepReport` (already has `swept_at`)
      persisted at `$FIELD_DATA_DIR/lifecycle/last_sweep.json`, 404 before
      any sweep. `lifecycle serve --every SECONDS` (default 0 = off; env
      `FIELD_LIFECYCLE_EVERY`): daemon thread, first tick after the interval,
      exceptions logged never raised (Fly's `wait -n` takes the machine down
      on any child exit), roster unset ⇒ a tick logged/ledgered as skipped,
      never a silent empty sweep. Outbound calls carry `auth_headers()`.
      `lifecycle sweep` CLI unchanged (shared engine builder). README: two
      rows replace row 43 — "Scheduler thread fires on the configured
      interval — Enforced in code when `--every`/`FIELD_LIFECYCLE_EVERY` AND
      `FIELD_LIFECYCLE_ROSTER` are set (injected-clock test)"; "The sweep is
      actually running on the estate — Declared only until a `swept_at` from
      the estate's `GET /findings` is on record (needs redeploy by Don)";
      LIMITS 54-55 rewritten; SPEC 25/27 dropped. *Done when:*
      `/lifecycle/health` OK in both smoke jobs; tests: `/sweep` without
      `auto_kill_orphans` (and with unknown keys → 422) leaves an orphan
      `active` with a kill spy at zero; grep-guard passes; no roster → 503;
      `--every` fires on an injected clock/short interval and a raising tick
      does not kill the thread; 401 without `x-field-auth` when the secret is
      set; suite green; demo.sh exit 0 < 60 s.
- [x] **A2 — attest serve.** New `attestation_reporter/api.py`
      `create_app(engine=None)` (default `PackEngine` from the same four env
      URLs as cli.py:44-47, `auth_headers()`), `install_authn`. `GET /pack`
      → `BoardPack` JSON (`period`/`org` query params accepted); `since`/
      `until` present ⇒ 422 "period window lands in C4" (explicit, never
      silently all-time); `GET /pack.html` → `HTMLResponse(render_html(...))`,
      PROTECTED like every data route (no `open_paths`; the console opens
      only a data-free shell) — README notes browsers on a secret estate
      cannot present the header. `attest serve --host --port 8013`; `render`
      shares the engine builder; PDF stays CLI. README row: "`GET /pack`
      served — an UNSIGNED, all-time draft until C4 (no window, no signer,
      no signature); since/until ⇒ 422"; LIMITS 51-55 kept until C4; LIMITS
      58 dropped. *Done when:* `/attest/health` OK in both smoke jobs;
      tests: `/pack` equals `attest render` JSON over the stack fixture;
      `?since=` → 422 (test named `test_pack_window_params_422_until_c4`, to
      be replaced in C4); `/pack.html` contains the rule sentence; governor
      down ⇒ metric `unavailable`; 401 under secret; suite green; demo.sh
      exit 0 < 60 s.
- [x] **A3 — crosswalk composed + `POST /pack`.** Wire the existing
      `crosswalk serve` (A0). `api.py`: `create_app(stale_store=None,
      fetcher=None)` (injection seam — today it takes nothing; D4 reuses it);
      `PackRequest(extra='forbid')`: `signer: str`, `manifest: dict`
      (REQUIRED in Phase A — nothing can resolve an agent_id to a manifest
      until B0; optionality lands in D4 after the resolver exists, README
      says so), `agent_id: str|None`, `sources: EvidenceSources|None`; the
      handler calls `generate_pack(...)` exactly as cli.py:176-178 — the CLI
      stays the canonical path and `POST /pack` is a thin adapter over it
      (README says so); `ValueError` (blank/whitespace signer) → 422;
      `StalePackError` → 409 with `{message, flags, affected_controls}` from
      `exc.flags`/`exc.affected`. Response `{markdown, pack}`. Also fix
      api.py:37-38 "Citations are stubs" (audit drift; D4 owns SPEC 13-15).
      *Done when:* `/crosswalk/health` OK in both smoke jobs; tests: signer
      '' and '   ' → 422; unknown key → 422; stale flag → 409 naming the
      framework and the same control ids `staleness.affected_controls`
      returns; happy path equals the CLI pack; 401 under secret; 42 existing
      tests unmodified; demo.sh exit 0 < 60 s.
- [x] **A4 — Fly memory.** `fly.toml` `[[vm]] memory = "2gb"` + comment
      (thirteen CPython processes; 1 GB was measured for ten); STATE.md
      "needs redeploy by Don". No deploy. *Done when:* tomllib parses;
      STATE.md line present.
- [x] **A-gate.** CLOSED 2026-09-12: suites, parse checks, demos and run_demo.sh (exit 0, 33 s) done; the independent adversarial review was re-run against ff1f836..ab4cd84 with two reviewers — both fix-first, no blockers, all findings applied in e89d289. See STATE.md. Original text:
- [ ] **A-gate.** lifecycle + attest + crosswalk + field-core + field-agent
      green; three CI jobs green on the pushed commit; `run_demo.sh` exit 0 +
      last 10 lines into STATE.md (run_demo.sh boots 7 local services and
      never starts these three — CI smoke is the proof of A; say so); demo
      wall times; adversarial review agent signed off; in-repo
      `tasks/lessons.md` gains the "probe /health from a separate call"
      rule; STATE.md phase record; summary → Don; STOP.

### Phase B — the authority chain (3, 4, 11)
Order B0 → (B1 ∥ B2) → B3 → B4; B4's kill-switch `retired` guard is applied
on top of B3's api.py, never in parallel. `agent_template.py` /
`05_rest_api.sh` are NOT touched in B (if a check-in example is added, it is
re-vendored + SOURCES.md stamp + plugin bump in the same commit); B-gate runs
`bash plugins/field-agent/verify_sync.sh`.
- [ ] **B0 — Shared manifest resolver (prerequisite for B1/B3/C2/C3).** Lift
      `ManifestResolver` verbatim from `conformance_sentinel/engine.py:109-144`
      into `field_core/clients.py` (`FIELD_MANIFEST_DIR` default `.`, mtime
      cache, None on missing/invalid) + module function
      `resolve_manifest(manifest_ref, manifest_dir=None) -> FieldManifest|None`
      + `resolve_manifest_detail(...)` returning `(manifest, reason)` with
      reason ∈ {`ok`, `no_ref`, `missing`, `invalid`} (C3 labels defaults
      with it). Deviation from spec B3 wording, flagged: the sentinel calls
      the field-core CLASS (kept exported from `conformance_sentinel.engine`
      for api.py:13, both conftests and field-agent conftest:16), not the
      free function, so `test_self_manifest.py:95-108`'s instance spy on
      `engine.manifests.resolve` stays valid — the free function wraps the
      same class: one resolver. Containers' WORKDIR is `/platform`, so
      relative refs resolve against `FIELD_MANIFEST_DIR=/data/manifests`
      (A0 passthrough); estate refs are absolute today. *Done when:* new
      `packages/field-core/tests/test_clients_resolve_manifest.py` (absolute,
      relative under manifest_dir, missing → None, invalid YAML → None,
      validation-invalid → None, mtime refresh, detail reasons); sentinel 59
      and field-agent 17 green with zero test edits.
- [ ] **B1 — delegation: DOA roster.** `FIELD_DOA_ROSTER` = YAML (manifests
      are YAML; PyYAML is a field-core dep; scopes are multi-word exact
      strings): `grantors: [{grantor, allowed_scope[], max_ttl_days,
      max_spend_usd?, active}]` parsed by a Pydantic model (`extra='forbid'`)
      in new `delegation_authority/doa.py`; documented in `docs/INTEGRATION.md`
      §3. Mint order (api.py:90-129 today) when the roster is set: roster load
      (missing/unreadable ⇒ 503 BEFORE any ledger write) → `granted_by` ∈
      roster and `active` else 403 `D.grantor` (exact string match) → scope
      ⊆ `allowed_scope` else 403 `D.grantor` → manifest via B0 from the
      registry record's `manifest_ref` (the record is already fetched at
      api.py:93 and discarded); no ref / missing / invalid ⇒ 422 `D.scope`
      (fail closed — README says so) → scope ⊆ `manifest.delegation.scope`
      else 422 `D.scope` → TTL ≤ `max_ttl_days` (both `ttl_seconds` and
      `expires_at` forms) else 403 `D.grantor`. `delegation.mint` payload
      gains `doa_checked` and `doa_row` (grantor, max_ttl_days). Roster unset
      ⇒ today's behaviour, `doa_checked=false`. `max_spend_usd` recorded,
      not enforced. New clause `D.grantor` in field-core with test. Ship
      `manifests/doa-roster.example.yaml`: Don as the only grantor, scope =
      union of both ssl manifests' scopes, `max_ttl_days: 30`.
      `FIELD_DOA_ROSTER` stays blank in compose/fly/CI (CI smoke mints for an
      agent without a manifest_ref). README:40 splits into two rows: "Mint
      refuses grantors, scopes and TTLs outside the roster — Enforced in
      code when `FIELD_DOA_ROSTER` is set (unset on both estates today)";
      "The caller is the named grantor — Declared only (`granted_by` is not
      authenticated; roster is exact-string membership)"; `max_spend_usd`
      "recorded, not enforced — Declared"; SPEC 26 split. demo.sh: register
      with a manifest_ref + export the roster + one refused mint. *Done when:*
      adversarial tests: grantor off-roster 403, inactive 403, scope beyond
      grantor 403, scope beyond manifest 422, TTL beyond max 403, roster set
      but missing → 503 with nothing persisted and no ledger event, agent
      without manifest_ref under a roster → 422; roster-unset path: existing
      8 tests unmodified, `doa_checked=false` asserted; CI smoke flow still
      mints; demo.sh exit 0 < 60 s.
- [ ] **B2 — delegation: OAuth-style introspection.** `POST /oauth/introspect`,
      body `application/x-www-form-urlencoded` parsed with
      `urllib.parse.parse_qs(await request.body())` (python-multipart is not
      installed; `Form()` would break `create_app()` for seven suites);
      missing `token` → 400. Active ⇒ `{active: true, scope, exp, iat, sub,
      client_id, token_type: "opaque", scope_list}` — `scope` is the RFC 7662
      space-delimited string and `scope_list` (an RFC-permitted extension
      member) carries the exact FIELD scope strings, because FIELD scopes
      contain spaces; README states both. Revoked/expired/unknown ⇒ exactly
      `{"active": false}`. Existing `/introspect` untouched. `token_type:
      "opaque"` is the spec's choice, not an RFC-registered value — README
      says so. CLI `delegation oauth-introspect <token>` (DoD: CLI verbs).
      One-liner word → "OAuth-style". *Done when:* tests assert the exact
      key set and types for active; `exp == int(expires_at.timestamp())`;
      `sub == client_id == agent_id`; revoked, expired (1 s TTL pattern) and
      unknown each return only `{"active": false}`; JSON body / missing
      token → 4xx; existing introspect tests unmodified.
- [ ] **B3 — kill-switch: resolvable endpoints + liveness.** (a) In
      `_kill_one` after `set_status` (api.py:114): B0 resolves the record's
      `manifest_ref`; new `EndpointResult{outcome: called|failed|skipped,
      reason, endpoint_host, method, http_status, elapsed_ms, error}` on
      `KillReport.endpoint_result`; ledger `kill.endpoint_called` /
      `kill.endpoint_failed` / `kill.endpoint_skipped`. Rules: allowlist
      `FIELD_KILL_ENDPOINT_ALLOWLIST` read per call; unset/blank ⇒ skipped
      `allowlist_unset`; host compare = `urlsplit(endpoint).hostname` exact
      match (defeats `http://169.254.169.254@allowed.host/` and
      `allowed.host.evil.com`); scheme must be http/https else skipped
      `non_http_endpoint` (covers `method: file`); method parsed from
      strings like `HTTP POST` → POST, unknown ⇒ skipped
      `unsupported_method`; SELF-CALL GUARD = BOTH an `x-field-kill-origin:
      kill-switch` header the service sends and short-circuits on, AND the
      `/kill/{agent_id}` / `/kill/domain/` path heuristic (so a genuine
      third-party hook on another host using that path is not false-skipped
      when the header is absent) ⇒ skipped `self_endpoint`; 2 s timeout;
      injectable `endpoint_client` seam; secrets in URLs never echoed (host
      only). Idempotent re-kill still sends the signal. (b) `kill_domain`
      refactored onto the same per-agent path; `DomainKillReport.results[]`;
      per-agent registry faults recorded, not 500; stays 200; N × 2 s serial
      bound documented (CLI timeout 30 s). (c) drill: `try/finally` restore
      with its own guarded restore (`restored: false` + ledger
      `kill.drill.restore_failed` if the restore itself fails); HTTPException
      branches raised inside the try; `DrillReport.endpoint_confirmed_ms:
      float|None` + `endpoint_result`; README notes a drill on an allowlisted
      estate sends a REAL halt signal. (d) `kill_switch/store.py`
      `HeartbeatStore` (SQLite, registry store pattern, `close()`), path
      `$FIELD_DATA_DIR/killswitch/heartbeats.sqlite3`, `create_app(...,
      heartbeats=None, clock=None)`; `POST /heartbeat/{agent}` records
      `last_seen` then answers with GET semantics (unknown ⇒ `killed=true`;
      unregistered check-ins recorded with status `unregistered` so shadow
      agents surface); `GET /heartbeat` never writes; `GET /liveness?
      stale_after=SECONDS` lists registry-active agents with no check-in in
      the window (`last_seen: null` counts as stale) and the live ones. (e)
      SDK minimal check-in — without it every agent on every estate reads
      stale forever: `LivenessClient.checkin()`, `FieldAgent.checkin()`,
      `fieldagent checkin`; demo agent and `tools/field-rest.ps1` gain the
      POST (SKILL docs note). README rows: "Resolvable kill endpoints —
      Enforced in code when `FIELD_KILL_ENDPOINT_ALLOWLIST` names the host;
      no shipped manifest declares an agent-side endpoint (all point at this
      service ⇒ skipped `self_endpoint`); both estates run with the allowlist
      unset ⇒ every kill ledgers `endpoint_skipped`"; row 50 "in-flight
      process stops — Declared only" KEPT (calling an endpoint is not the
      process halting); "Heartbeats — server-side liveness Enforced for
      agents that POST check-ins; stale = no check-in in the window, not
      evidence the process is dead; no agent checks in on either estate
      until SDK/skills redeploy"; ARCHITECTURE kill-switch row no longer
      "stateless". *Done when:* adversarial: manifest endpoint
      `http://169.254.169.254/latest/meta-data` with allowlist unset AND with
      `allowlist=example.com` ⇒ endpoint fake records zero calls, ledger
      `kill.endpoint_skipped`, kill still 200; userinfo and suffix-host
      tricks skipped; header-marked self call skipped; allowlisted host +
      fake `ConnectionError` ⇒ 200, killed, `failed`, ledger
      `kill.endpoint_failed`; allowlisted host + 200 ⇒ `called`; domain kill
      with one failing endpoint ⇒ 200 with mixed results; drill: fake
      raising after the flip ⇒ 500 AND status back to `active`; existing 8
      kill-switch tests unmodified; liveness: A checks in, B never ⇒ B
      stale; frozen clock advances A past the window ⇒ A stale; killed agent
      checking in still gets `killed=true`; second `create_app` on the same
      store resumes `last_seen`; sentinel 59 + field-agent 17 green on B0;
      demo.sh exit 0 < 60 s.
- [ ] **B4 — lifecycle: attested_at, provision, decommission.** Registry:
      `attested_at`, `attested_by` on `AgentRecord` only (not on
      Create/Update — `extra='forbid'` stops PATCH forging them); SQLite
      migration in `RegistryStore.__init__` (`PRAGMA table_info` → `ALTER
      TABLE ADD COLUMN`; the persisted GB10/Fly DBs are not recreated) and
      the positional INSERT (store.py:62) becomes named-column; `POST
      /agents/{id}/attest` body `{attested_by}` stripped, blank/whitespace →
      422, unknown → 404, ledger `registry.attested`; `registry attest <id>
      --by NAME` CLI; registry README adds a Declared row "attested_by is
      the human who attested — Declared only (recorded string, not
      authenticated)". Lifecycle re-attestation basis = `attested_at` else
      `created_at`, NEVER `updated_at` (grep-guard test); `ReattestationDue`
      gains `basis` + `attested_by`; payload keys additive. `lifecycle
      provision --manifest --owner --domain --grantor --ttl-days [--name]
      [--manifest-ref]` (the two extra flags reproduce today's registry
      records: display name and estate path) in `engine.provision(...)` with
      injected clients: `validate_manifest_file` (INVALID ⇒ exit 1, zero
      side effects) → register (409 ⇒ PATCH owner/manifest_ref, reported as
      `updated`) → cap via `SpendCapConfig.from_manifest` (lifecycle-manager
      gains `spend-governor` as a runtime dependency — precedent field-agent
      → conformance-sentinel; the requirement string must equal the dist
      name in `services/spend-governor/pyproject.toml`; one cents rule,
      `round`, not `int()`) → mint (B1's 403/422/503 pass through verbatim);
      `ProvisionReport` JSON with `token_id`; partial failure reported step
      by step, never pretended atomic. `lifecycle decommission <agent> --by
      NAME --reason`: `registry.get_agent` (unknown ⇒ exit 1, nothing
      created) → if already `retired` ⇒ ledger `lifecycle.decommissioned{noop:
      true}` and exit 0, no kill → revoke every active token (a 502 from a
      ledger-first revoke is reported and the run continues act-first, exit
      non-zero at the end) → kill via B3 only if status is `active` (an
      already-killed agent gets no second `kill.agent`) → registry `retired`
      → ledger `lifecycle.decommissioned{by, reason, tokens_revoked, killed}`.
      Protect `retired` cross-package: kill-switch `/kill`, `/kill/domain`,
      `/revive` answer 409 / skip for retired agents (README: "retired agents
      are already non-active — heartbeat `killed=true`, sentinel blocks —
      `/kill` answers 409 instead of flipping retired→killed so a retire
      cannot be undone by a later revive") and the console hides `revive`
      for them. `tools/provision_ssl_agents.py` → thin wrapper: keeps
      `FIELD_PROXY_URL`/secret/tokens-file contract, the 6-service health
      gate, the AGENTS table and every probe; calls `lifecycle provision` per
      agent; drops its own PUT /caps and POST /tokens; the out-of-repo
      `_local-test/provision_local.py` pointer (file lives untracked in the
      parent folder) is annotated "local path is now `lifecycle provision`".
      *Done when:* adversarial: decommission unknown agent fails loud
      (registry unchanged, no ledger event, kill spy zero); second
      decommission is a no-op with the ledger note and no second
      `kill.agent`; PATCH cannot set `attested_*` (422) and does not reset
      the re-attestation clock; blank attest name 422; store migration test
      on an old 8-column DB; provision of an INVALID manifest has zero side
      effects; happy-path provision yields registered + cap 50000 cents daily
      + one token with the manifest scope; kill/revive of a retired agent
      409; existing 8 kill-switch and 8 console tests unmodified; both Docker
      images build in CI; wrapper's probe function passes against the
      in-process stack; suites green; demo.sh exit 0 < 60 s.
- [ ] **B-gate.** delegation + kill-switch + lifecycle + registry + sentinel +
      console + field-core + field-agent green; `verify_sync.sh` green; CI
      green on push; `run_demo.sh` exit 0 + tail in STATE.md (FIELD_DOA_ROSTER
      unset there); demo wall times; adversarial review; STATE.md incl.
      "needs redeploy": registry migration forward-only (back up
      `/data/registry`), allowlist, roster; summary → Don; STOP.

### Phase C — record and proof (5, 6, 12)
File ownership: subagent 1 = ledger C1+C2 (+ the lifecycle finding and the
attest metric C2 adds, merged before C4 starts); subagent 2 = replay C3;
subagent 3 = attest C4 (after C2's metric lands).
- [ ] **C1 — ledger: auditor export.** `POST /export` and `ledger export`
      accept `since`, `until`, `agent_id`, `event_type` (reuse
      `LedgerStore.events()`; the lexical ts compare becomes
      `datetime.fromisoformat` with inclusive bounds + a regression test —
      replay 5 and attest 7 tests must stay unmodified and green). Bundle dir
      `out_dir/<stamp>/`: `events.jsonl` (lines are PURE `LedgerEvent` JSON —
      `extra='forbid'` and the hash recompute forbid any extra key),
      `summary.json` (+ `first_index`, `last_index`, `head_index`),
      `chain_proof.json` = `{first_index, last_index, head_index,
      first_prev_hash, head_hash, verification (of the FULL live chain at
      export time), filters, spine}` where `spine` = `[{index, event_id,
      prev_hash, hash}]` for every event in `[first_index, head_index]`;
      `signature.json` = Ed25519 over canonical `summary + chain_proof` via
      `field_core.signing` when `--sign-key` is given (CLI only; the served
      route writes `signed: false`), with `key_fingerprint` (new field-core
      helper: sha256 over the raw 32-byte public key). Honest claim: a
      filtered bundle proves the exported events sit at the claimed
      positions of a chain whose spine the SIGNER attests; the served
      (unsigned) bundle proves internal consistency only — `verify-export`
      prints "spine unverified (unsigned)"; independent proof = compare
      `chain_proof.head_hash` with an off-box anchor. `ledger verify-export
      <dir> [--pubkey]`: recompute exported hashes, walk the spine links to
      `head_hash`, counts, signature; exit 1 names the first failing index;
      unsigned + `--pubkey` fails. README export row → "re-verifiable
      offline (hashes + spine); Ed25519-signed only via `ledger export
      --sign-key` — the served `/export` is unsigned (`signed: false`)"; row
      40 (per-event signatures) stays Declared until F2.
      `test_export_summary_counts:105` is updated to
      `Path(summary["path"]).exists()` under `out_dir/<stamp>/` — assertion
      tightened, none removed; the other 10 ledger tests unmodified. *Done
      when:* editing one exported event fails `verify-export` naming the
      index; deleting a line fails; a filtered (agent_id) export of an
      interleaved 2-agent chain verifies via the spine and reports "spine
      unverified" when unsigned; tampering `summary.json` on a signed bundle
      fails; wrong key fails; CLI via `CliRunner`; demo.sh exit 0 < 60 s.
- [ ] **C2 — ledger: retention by rotation (DESIGN approved here, then built).**
      Facts: one shared chain per estate, so per-agent deletion cannot exist;
      `make_event(prev_hash=…)` and `_head_hash` already give "genesis =
      previous head"; `verify_chain` hard-codes GENESIS (`field_core/
      ledger.py:80`) → gains `genesis=` (field-core, tested); the path given
      to `LedgerStore` is the OPEN segment whatever its name (three suites
      open `e.jsonl`), closed segments are `<stem>-<n><suffix>` beside it,
      the manifest is `<stem>.segments.json` in the same directory:
      `[{n, file, start_index, end_index, genesis_prev_hash, head_hash,
      closed_at, anchor, archived_to?}]`. Writer safety: `append()` under the
      lock stats the open file and re-runs `_recover_head` on size mismatch
      (closes today's second-writer fork hazard); readers (`events()`,
      `verify()`, health count, export) take the lock and fully materialise
      before releasing (Windows: `os.rename` fails with WinError 32 while a
      generator holds the file — verified by the reviewer); the segments
      manifest is re-read (mtime-cached) on every read/verify. `ledger
      rotate`: under the lock, rename the open file (retry 5 × 100 ms on
      `PermissionError`, then 503 "ledger busy" with nothing renamed), append
      a signed `AnchorRecord` (gains optional `segment`; old records stay
      valid) with `FIELD_LEDGER_ANCHOR_KEY` (PEM path under `/data`; unset ⇒
      503 "no anchor key configured" — never an unsigned rotation), write the
      segments entry, open a fresh segment whose FIRST event is the rotation
      event with `prev_hash` = previous head (self-describing). Served `POST
      /rotate` (operator + reason, ledgered) uses the same key; CLI
      rotate/hold/retention verbs delegate to the served routes when
      `FIELD_LEDGER_URL` is set, else refuse unless `--offline` (service
      stopped). `verify` walks segments in order, reports `segment n +
      global index` on a break; global index never renumbers;
      `ChainVerification` gains `segments`, `archived_segments`,
      `verified_events` (`length` stays the global chain length — console
      and replay print it); `/events`, `/export`, `/health` span live
      segments; `/health` and `/retention/check` expose
      `earliest_live_index` / `earliest_live_ts`. Anchors:
      `LedgerStore.global_length()` and `hash_at(global_index) → hash |
      "archived" | None`; `write_anchor` uses `global_length()`;
      `verify_anchors` uses `hash_at` — an anchor positioned inside an
      archived segment is an explicit failure naming segment n +
      `archived_to`, never a silent pass. `ledger retention apply --days N
      [--archive-dir D]`: default `D = $FIELD_DATA_DIR/ledger-archive` (env
      `FIELD_LEDGER_ARCHIVE_DIR`), refuse a dir outside `FIELD_DATA_DIR`
      unless `--allow-external` and any dir inside the live ledger dir;
      moves CLOSED segments whose `closed_at` is older than N days
      (`shutil.move`, same filesystem documented; never the open segment)
      and writes a sidecar `<file>.segment.json` beside each; refuses (exit
      4) when the legal hold exists; entry keeps `archived_to`; ledger
      `ledger.retention.applied`; idempotent. `ledger verify --path X`: the
      open file of a manifest ⇒ full walk; a closed entry or a sidecar ⇒
      verify from its `genesis_prev_hash` and compare `head_hash`; else
      single-file from GENESIS (video scripts unchanged); `--genesis HASH`
      escape hatch on `ledger verify` and `field verify-chain`. Legal hold:
      `$FIELD_DATA_DIR/ledger/legal_hold.json {placed_by, reason, placed_at}`
      via `ledger hold place --by NAME --reason` / `ledger hold release --by
      NAME` (blank names refused), ledger `ledger.legal_hold.placed/
      released`. `ledger retention check` + `GET /retention/check`: estate
      policy `FIELD_LEDGER_RETENTION_DAYS` (A0 default 2555 on compose/fly;
      unset on a bare install ⇒ "no estate policy", exit 3) vs max
      `ledger.retention_days` across registered manifests (registry list →
      B0 resolve inside the ledger container; agents with NO manifest_ref are
      skipped and counted separately — only a SET ref that fails to resolve
      is `unresolvable` ⇒ exit 3); `SweepReport.retention_policy:
      RetentionFinding|None` in lifecycle, included in the exit-3 predicate
      and A1's persisted `/findings`; the board pack gains TWO scalar metrics
      ("Estate ledger retention policy (days)" int/unavailable; "Manifests
      declaring more retention than the estate keeps" int, offending ids +
      unresolvable refs in `note`) because `Metric.value` is scalar-only.
      README truth: retention is ESTATE-level; per-manifest `retention_days`
      is a floor the estate must meet, not a per-agent purge; archived
      segments are verified by manifest link only — the manifest is not
      tamper-evident; the signed rotation anchor (shipped off-box) pins each
      closed head; the hold marker is only as strong as file access
      (Declared); on-box key ⇒ tamper-evidence only against actors without
      box access. *Done when:* rotate twice → verify OK across 3 segments,
      global length = total; a store opened as `e.jsonl` rotates correctly;
      reader mid-iteration in another thread, then rotate ⇒ success or 503,
      never a half-rotated directory; second-writer size-mismatch test;
      tamper inside a live closed segment ⇒ verify names segment + index;
      genesis link edit ⇒ break at its first index; editing an archived
      entry's `head_hash` in the manifest breaks live verify at the next
      segment's first index; pre-rotation anchor still verifies; an anchor
      inside an archived segment ⇒ explicit failure; `/events?agent_id`
      spans segments; archival keeps live verify OK and the archived file
      verifies standalone via its sidecar; hold blocks apply (exit 4,
      listing unchanged); blank hold name refused; rotate without a key ⇒
      503; estate 365 vs manifest 2555 ⇒ exit 3 naming the agent; no-ref
      agent skipped; unresolvable set ref ⇒ listed + exit 3; lifecycle
      finding present + exit 3; attest metrics present, ledger down ⇒
      unavailable; the 10 dependent suites unmodified and green;
      `field verify-chain` single-file behaviour documented; demo.sh exit 0
      < 60 s.
- [ ] **C3 — replay: RACI from data.** `TimelineEntry` gains `action` and
      `enforced`; `clause_id = payload.get('clause_id') or payload.get
      ('would_block')`; `first_failure` includes `conformance.shadow_block`/
      `shadow_escalate` (exact strings from sentinel engine.py:185), labeled
      "(log-only, not enforced)" in summary and markdown. R = registry owner
      (unchanged). A = among window-overlapping grants, the one whose scope
      contains the failing action (exact string membership — the sentinel's
      rule, engine.py:406-408 / `DelegationToken.covers`), earliest if
      several; label `(grant covering '<action>')`; else earliest overlapping,
      label `(earliest overlapping grant)`; a `D.scope` failure by
      construction has no covering grant → fallback (test proves both
      branches). C = `enforcement.kill_switch.authorized_operators` when
      NON-EMPTY (templates ship `[]`), label `(manifest kill_switch
      .authorized_operators)`; else `CLAUSE_EXEC[letter] (default)`. I =
      `identity.principal` (+ ` — org`), label `(manifest identity)`; else
      the current string + `(default)`. Manifest via B0 injected into
      `ReplayEngine(manifests=…)`; `PostMortem.manifest_resolved` +
      `manifest_detail` (reason from B0); `raci_sources` map (additive);
      token/ledger timestamps compared via `datetime.fromisoformat`. After
      C2: an integrity note "window starts before the earliest live event
      (segments archived: n)" when `since < earliest_live_ts` from
      `/health`. demo.sh registers a manifest_ref. README rows Enforced only
      with the per-source/per-fallback tests; sentinel README lists replay as
      shadow-aware. One-liner keeps "RACI" with sources named. *Done when:*
      tests: covering grant beats an earlier non-covering grant; D.scope ⇒
      earliest-overlapping label; no grants ⇒ `<no grantor found>`;
      operators non-empty ⇒ manifest label; `[]` / no ref / missing file /
      invalid manifest ⇒ `(default)` with `manifest_resolved=false`, no
      crash; principal+org and principal-only labels; shadow_block with
      `would_block: D.scope` ⇒ first failure `D.scope` labeled log-only,
      Consulted from letter D; ordering enforced-vs-shadow both ways;
      earliest-live note present; existing 5 tests unmodified; demo.sh exit
      0 < 60 s.
- [ ] **C4 — attestation: period window + signature.** `window.py`:
      `parse_period("2026-Q3" | "Q3 2026")` → UTC quarter `[since, until]`
      (until = last day 23:59:59.999999); `normalise_bound` (date-only
      expands to start/end of day; `Z` → `+00:00`; naive = UTC) matching the
      ledger's inclusive bounds; `--period` and `--since/--until` mutually
      exclusive; neither ⇒ all-time, labeled `window.kind='all-time'`;
      `demo.sh:49` and `run_demo.sh:116` free-form captions replaced by a
      window derived from `date` (current quarter, or `--since/--until` ±1
      day around now — never a literal quarter). EVERY ledger-derived metric
      (10 `_event_count` + the derived rate today, + the 2 lifecycle rows =
      13; the test iterates `all_metrics()` and asserts `since=`/`until=` on
      each whose `source_query` hits `/events`) carries the window; token
      metrics stay point-in-time with a note; governor open escalations,
      registry counts, integrity and the 30-day expiry get "point-in-time:
      at generation" notes (Metric gains `basis: window|point_in_time`).
      Signature: `BoardPack` gains `signed=False, signer, signed_at,
      key_fingerprint, signature`; `sign_pack` refuses a blank signer; bytes =
      `canonical_manifest_bytes(pack.model_dump(mode='json',
      exclude={'signature'}))` — never a dict with `signature=None` — so
      every metric name/value/unit/source_query/status/note, window and
      `generated_at` are inside the signature; verification canonicalises
      the raw parsed JSON after the same round-trip, never a re-validated
      model; only `board-pack.json` is the signed artefact. `attest render
      --signer NAME --sign-key PEM`; HTML footer prints signer + fingerprint;
      unsigned ⇒ `UNSIGNED DRAFT` banner right after `<body>` + `signed:
      false`. `attest verify pack.json --pubkey PEM` (exit 0/1; unsigned ⇒
      "nothing to verify", key mismatch named). Served `/pack` honours
      `since/until/period`: A2's `test_pack_window_params_422_until_c4` is
      deleted, the A2 README row rewritten to "windowed, unsigned draft", the
      A2 LIMITS sentence dropped; served packs are ALWAYS unsigned drafts (an
      unattended server cannot be the named human signer — F4 revisits).
      Expirations: new section "Expirations & re-attestation" with the
      30-day token metric moved in, plus windowed counts of
      `lifecycle.reattestation_due` and `lifecycle.expiring_authority` events
      — note states these are sweep EVENTS (finding-days under a daily A1
      schedule), plus a de-duplicated "distinct agents/tokens flagged"
      metric with the formula printed. Earliest-live note as in C3. Fix the
      time-bomb: `test_pack_numbers_match_staged_state` uses an explicit
      window around NOW. *Done when:* hand-chained `events.jsonl` with ts on
      both sides of the quarter ⇒ only in-window events counted, integrity
      INTACT; every ledger-derived `source_query` contains `since=`/`until=`;
      all-time build has none; mutating ANY metric field, `signer`,
      `signed_at`, `period`, `window.since` or `generated_at` in the dumped
      JSON invalidates the signature; wrong key fails; blank signer refused;
      banner present unsigned, absent signed; footer names signer +
      fingerprint; `verify` CLI exits 0/1/1(unsigned); lifecycle rows
      counted in-window with the honesty note; ledger down ⇒ `unavailable`;
      served `/pack?since&until` works; run_demo.sh board-pack scene exits
      0; demo.sh exit 0 < 60 s.
- [ ] **C-gate.** ledger + replay + attest + lifecycle + field-core +
      field-agent green; CI green on push; `run_demo.sh` exit 0 + tail (an
      unsigned run renders the banner — say so); demo wall times;
      adversarial review; STATE.md incl. "needs decision by Don":
      `FIELD_LEDGER_RETENTION_DAYS` per estate, anchor-key custody, archive
      dir; summary → Don; STOP.

### Phase D — the enforcement words (9, 10, 1, 7, 8)
File ownership: subagent 1 = D1 (governor + sentinel step 8 + field-agent
retry_after); subagent 2 = D2 (gateway + `field_core/llm.py` + the three
callers' base-URL lines); subagent 3 = D3 (registry); subagent 4 = D4
(crosswalk regwatch); subagent 5 = D5 (federation + field-agent
federation.py). Shared files are serialized AFTER module work: compose /
entrypoint / ci.yml / .env.example / IMPLEMENTATION §3 edits D2 → D4 → D5;
`field-agent` cli.py + README merged D1 then D5; sentinel README merged D1
then D2; crosswalk `suggestions.py` (D2) and `api.py/cli.py` (D4) are
different files.
- [ ] **D1 — governor: throttle.** (a) `set-cap --from-manifest` also loads
      `enforcement.rate_limits` into a NEW table `rate_limits(agent_id,
      action, max, period_seconds)` via `PUT/GET /rate-limits/{agent}`
      (keeps `SpendCapConfig` `extra='forbid'` stable for every caller);
      period grammar = `hourly|daily|monthly|<N>s|m|h|d`; the templates'
      `session` has no server-side meaning and is recorded as
      `declared_unenforced` with a loud CLI warning and ledger
      `spend.rate_limit_declared_unenforced` — NEVER mapped to `total`;
      action `tool_call` is NOT a wildcard (the per-action key must equal
      `req.action` verbatim; LIMITS: judge-affirmed paraphrases on judge-on
      estates are not counted against a limit); a manifest with
      rate_limits but no spend_cap is refused loudly (today's rule). (b)
      Counting source: `SpendRequest` gains optional `action` (and `source`),
      the spend table gains `action`/`source` columns via a `GovernorStore.
      __init__` migration (PRAGMA → ALTER TABLE; the positional INSERT at
      core.py:201 becomes named-column; test on an old 7-column DB — the
      persisted GB10/Fly `spend.sqlite3` is not recreated); SDK
      `report_spend(..., action=None)`, `invoicing_agent.py:72` passes
      `action="draft invoices"`, `Send-FieldSpend -Action` — without these
      no SDK agent ever feeds a per-action window; the token window reuses
      `store.window_tokens` with `retry_after` = seconds until enough oldest
      rows age out. `SpendState.THROTTLED`; `SpendStatus` gains
      `retry_after_seconds`, `throttled{action,count,max,period}`; `GET
      /status/{agent}?action=`; precedence BLOCK(cap) > THROTTLED > ESCALATE
      > OK; governor judge gates keep `is SpendState.BLOCK` (api.py:204,
      :306) and the sentinel keeps `== "BLOCK"` at engine.py:272 and :469 —
      THROTTLED does not pause judgments (stated). (c) Sentinel:
      `SpendStatusClient.status(agent_id, action=None)` (keyword; the
      judge-gate call at engine.py:259 stays single-positional for
      `test_judge.py:171`'s fake); step 8 maps THROTTLED → BLOCK
      `E.rate_limit` (EXISTING clause — pinned by a new field-core test)
      with `extra_context={'retry_after_seconds': …}` threaded through
      `_verdict` into enforce context, shadow context and the ledger payload
      — log-only shadowing is automatic. (d) SDK: `ActionBlocked.retry_after`
      property reading `verdict['context']['retry_after_seconds']` (keeps
      the identity contract — the class stays the sentinel's own);
      `SpendStatusLite` gains `retry_after_seconds`; `fieldagent check`
      prints it, exit code stays 1 (BLOCK); `agent_template.py` re-vendored
      + SOURCES.md stamp + plugin bump in the same commit if it changes. (e)
      Clock seam: `spend_governor.api.create_app(store=None, ledger=None,
      clock=None)`; the four inline `datetime.now` calls use
      `app.state.clock`. (f) README rows: "THROTTLED after N reported actions
      in the window — fed by self-reported per-action counts (row 68 caveat
      applies) for periods the governor can parse; `session` is
      Declared/gate-only; sentinel metering is a proposal"; the governor
      stays "the meter, not the gate" (no 429 in-line); row 68 stays
      Declared. The demo manifest `integration/demo/manifests/
      invoicing-agent.yaml` (+ byte-identical plugin copy `example-manifest-
      invoicing-agent.yaml` + SOURCES.md stamp + `plugin.json` 0.1.2 in the
      SAME commit) gains a parseable entry that limits an action the demo
      never exhausts (`read timesheets`, hourly 10) so the word has a live
      instance without touching the 5th-draft ESCALATE story (a test asserts
      run_demo's 5th-draft ESCALATE). *Done when:* frozen-clock tests: N
      allowed, N+1 THROTTLED with `retry_after_seconds` = 1 at T+period−1 s,
      OK at T+period; token window likewise; cap BLOCK outranks THROTTLED;
      `?action=` for an unlimited action not throttled; case/whitespace
      variants not matched; `session` entry loads the cap, records
      declared-unenforced, never locks out; unknown period string rejected;
      old 7-column `spend.sqlite3` migrates; sentinel: exhausted window ⇒
      BLOCK `E.rate_limit` with context and ledger payload, log-only ⇒ ALLOW
      + shadow `would_block: E.rate_limit`, per-action isolation; SDK:
      `ActionBlocked.retry_after` equals the governor's value, `report_spend
      (action=…)` feeds the window, THROTTLED status surfaced; re-export
      identity test still passes; governor 19 + sentinel 59 + field-agent 17
      existing tests unmodified; demo.sh exit 0 < 60 s.
      **Plan-mode PROPOSAL (Don decides; not built until decided):** the
      sentinel posts `actions=1, action=<req.action>, source=sentinel,
      shadowed=<bool>` to the governor on EVERY response returned as ALLOW in
      EITHER mode (the action runs either way; log-only windows must fill so
      `would_block: E.rate_limit` can be observed) — never on BLOCK/ESCALATE
      — best-effort after the verdict; the post is SKIPPED when the step-8
      status was None (uncapped agent ⇒ `/spend` 404s) with
      `metered: false, reason: no_cap` in the verdict context; a post failure
      is ledgered as a metering gap and never flips the verdict; the
      `spend.recorded` doubling per check is stated in LIMITS (or a
      `source=sentinel` path omits it). Double-counting today (re-verified):
      integration demo `invoicing_agent.py` — 5 ALLOWs (incl. the unreported
      `read timesheets`) + 4 self-reports ⇒ `spent_actions` 4 → 9 (the cents
      96 % escalation story is unchanged); dogfood skills via
      `tools/field-rest.ps1` — `Invoke-FieldCheck` per action AND
      `Send-FieldSpend -Actions N` (operator-typed) ⇒ up to 2×;
      `agent_template.py:73` (plugin-mirrored) true 2×;
      `packages/field-agent/examples/02_usage.py` self-reports without ever
      checking — the UNDER-count case if metered rows took precedence per
      agent. Options: (A) precedence per (agent, action): a window counts
      sentinel-metered rows for that action when any exist in the window,
      else self-reported rows for that action; rows with `action=None` count
      toward totals only; expose `spent_actions_self` /
      `spent_actions_metered`; the `action_limit` cap uses max(self,
      metered) per action + unattributed self rows — no double count, no
      under-count, both totals visible; (B) drop `actions` self-reports in
      the in-repo callers (demo agent, template + plugin re-vendor, ps1/SKILL
      hook 2 becomes cents-only) — do this NOW on top of A, not as a follow-
      up, so the dogfood board pack is right on day one; (C) leave both and
      accept the inflation (rejected). Recommendation: A + B. If adopted:
      adversarial tests — metered A + self-reported B ⇒ B counts 1; both for
      A ⇒ 1; governor-post failure ledgered, verdict not flipped; uncapped
      agent ⇒ no post, `metered: false`.
- [ ] **D2 — gateway.** (a) `TelemetrySummary` keeps every count and gains
      `rates: {route: {window: RouteRates}}` with `confidence_tag_rate`,
      `flattery_free_rate`, `cot_structure_rate` as `None` (not 0.0) when
      `requests == 0`; windows = `all` and `last_N` (count-based, N =
      `FORCE_TELEMETRY_WINDOW`, default 50 — deterministic like the rest of
      the service) plus `_all` route; a second injectable upstream that
      returns flattery/no tags makes rates non-trivial in tests; method label
      rides the payload. (b) `DriftTracker` keyed by `(route, dimension)`;
      `record(route, dimension, score, model, rubric)`; two series fed
      (`overall`, `sycophancy`); `DriftAlert.dimension`;
      `gateway.drift_alert` payload names it; `hygiene_trend` nests
      `{route: {dimension: …}}`, `active_alerts` = `[{route, dimension}]`;
      `MockHygieneJudge` accepts per-dimension score dicts; the existing
      delta tests are updated in the same commit so that alert count per
      episode per (route, dimension) == 1 — filtered by dimension, each
      == 1, total == number of series fed, never relaxed to `>= 1`/`any()`;
      `test_single_bad_window_then_recovery_never_alerts` asserts `[]` for
      every dimension. With the judge off (both estates) there is still no
      sycophancy signal — Enforced as mechanism, README says so. (c)
      `force_gateway/store.py` `GatewayStore` (SQLite, `close()`):
      `telemetry_records`, append-only `drift_scores(route, dimension, score,
      model, rubric, ts)` replayed into the tracker at startup, `counters`
      (request_count for the sampling stride, coverage counters — not
      `bypass_remaining`); path `$FIELD_DATA_DIR/gateway/telemetry.sqlite3`;
      `create_app(store=None)`; `/telemetry` reads the store;
      `FORCE_TELEMETRY_RETAIN` cap + LIMITS line; a store fault bypasses like
      any instrumentation fault; `services/force-gateway/demo.sh` exports a
      mktemp `FIELD_DATA_DIR` (cygpath form, as field-agent demo.sh does) and
      sleeps 1 s before cleanup. (d) compose: drop `--mock`; forcegw env
      passthroughs from A0 make `FORCE_GATEWAY_MOCK=1 docker compose up -d`
      in ci.yml effective PLUS a roundtrip assertion (`POST /gateway/v1/
      messages` → mock model id; health alone would pass even keyless);
      `demo.sh:17` uses the env var; `--mock` CLI flag kept. Consequence
      (STATE.md "needs decision by Don"): the GB10 flips from `mock: true` to
      keyless-real on its next deploy — 502 on `/v1/messages` until
      `ANTHROPIC_API_KEY` is set in the GB10 .env (now forwarded); with
      `FORCE_GATEWAY_URL` estate-wide a judge-on sentinel depends on forcegw
      holding the key. Unit tests for the real-upstream keyless 502 (zero
      tests today) and for `FORCE_GATEWAY_MOCK='true'` NOT mocking. (e) New
      `field_core/llm.py`: `anthropic_base_url()` = `FORCE_GATEWAY_URL` else
      `ANTHROPIC_BASE_URL` else default, trailing slash normalised;
      `anthropic_headers(key)` merges `auth_headers()` so a secret estate's
      gateway accepts the call; the three callers (`judge.py:139`,
      `suggestions.py:173`, `hygiene_judge.py:98`) use it; the FOURTH reader
      `force_gateway/api.py:76` (the gateway's own upstream) keeps reading
      `ANTHROPIC_BASE_URL` directly and MUST NOT use the helper (test:
      `FORCE_GATEWAY_URL` set does not change `real_upstream`'s base).
      RECURSION guard: platform callers send `x-force-passthrough: judge`;
      the gateway forwards such requests uninstrumented (no injection, no
      telemetry, no sampling) and counts them in `coverage.passthrough`;
      the header is honoured only with a valid `x-field-auth` when
      `FIELD_SHARED_SECRET` is set; on a secretless estate it is honoured but
      every passthrough is ledgered `gateway.passthrough{client_host}` and
      LIMITS states any client can self-exempt there; README states platform
      judge traffic is deliberately excluded from hygiene telemetry. compose
      anchor `FORCE_GATEWAY_URL: http://forcegw:8009` (also in the gb10
      override's restated sentinel env); entrypoint `http://127.0.0.1:8009`;
      `FIELD_GATEWAY_URL` keeps its CLI meaning (both documented). (f) README
      LIMITS "no streaming" line (README.md:98) kept verbatim. *Done when:*
      rates tests (mixed responses → 0.5; zero requests → None; last_N moves,
      all does not); sycophancy drifts while overall holds ⇒ exactly one
      alert with `dimension: sycophancy`, and the converse; independent
      baselines; model change resets both; persistence: second `create_app`
      on the same store resumes counts, baselines, stride and alert state;
      two data dirs isolated; corrupt store ⇒ 200 + bypass; env-var mock
      precedence tests; base-URL precedence in all three callers; fourth
      reader unaffected; `x-field-auth` attached when the secret is set
      (in-process gateway TestClient 200 not 401); passthrough forwarded
      untouched and not counted in `by_preset`; passthrough from an
      unauthenticated client under a secret is ignored (instrumented,
      counted); nested judge cannot re-sample; grep confirms the streaming
      LIMITS line; compose-smoke roundtrip green on push; demo.sh exit 0
      < 60 s.
- [ ] **D3 — registry: API-key scanner.** `scan_api_keys(csv_text, registered,
      known_principals=None) -> (candidates, scanned)` over
      `key_name,owner,service,created,last_used[,last_used_by]` — the spec's
      column set has no principal column and `last_used` is a timestamp, so
      "last used by unknown principal" needs the OPTIONAL `last_used_by`
      column (extras ignored); rules with distinct reasons: blank owner ⇒
      `unowned API key`; owner ∉ registry owners (case-insensitive exact,
      lifecycle's `parse_roster` rule) ⇒ `owner is not a registered agent's
      owner` — applies EVEN when `key_name` matches a registered agent;
      `last_used_by` ∉ owners ∪ agent ids/names ⇒ `last used by unknown
      principal`; owner match ⇒ not surfaced. Optional `--principals
      owners.csv` widens the known set (IAM exports carry emails, registry
      owners are names — expected false positives, LIMITS).
      `scan_secrets_text(text)`: ordered `KEY_PATTERNS` with boundaries and
      breadth labels — `sk-ant-` (low FP), `sk-`/`sk-proj-` (BROAD, after
      sk-ant-), `AIza` (39 chars, low), `hf_` (moderate), `AKIA|ASIA` (low),
      `gh[pousr]_` (low), `xox[baprs]-` (low), `sk_(live|test)_` (low),
      `ya29.` (low), JWT-shaped (generic); the very-broad
      `(api_key|secret|token)=` assignment pattern ships OFF by default;
      every hit is REDACTED at the model layer (prefix 7 + last 4 + sha256
      fingerprint); input capped at 1 MiB. `DiscoverRequest` gains
      `api_keys_csv`, `secrets_text`, `principals_csv` and `extra='forbid'`
      (a typo'd field must 422, not scan nothing); `DiscoveryReport` gains
      `scanned_api_keys`, `scanned_secret_hits` (defaults keep old tests);
      `registry scan --api-keys FILE [--secrets-text FILE] [--principals
      FILE]`; fixtures are obviously synthetic (`sk-ant-api03-SYNTHETIC…`
      padded to the length floor — GitHub push protection). README:37
      "knows about all agents" STAYS Declared; new Enforced row "file-based
      credential-inventory and secrets-text scan (labeled heuristic)"; LIMITS
      names the broad patterns and "no live IAM/cloud/secret-manager
      connector — export the inventory yourself"; SPEC:26 stale "no ledger
      emission" fixed. *Done when:* adversarial: a key named
      `invoicing-agent-prod` with owner `growth@example.test` is surfaced
      with the owner reason although `invoicing-agent` is registered; owner
      match not surfaced; blank owner surfaced; unknown `last_used_by`
      surfaced; each provider pattern detected on synthetic values;
      `sk-ant-` not double-counted as `sk-`; raw fixture values never appear
      in the response JSON; broad patterns labeled; `/discover` with only
      `api_keys_csv` → 200, `{}` → 422, typo'd field → 422; CLI exit 3 on
      candidates (first CLI test); existing 8 tests unmodified; demo.sh exit
      0 < 60 s.
- [ ] **D4 — crosswalk: continuous.** New `regwatch.py`: source inventory
      derived from `CONTROLS` (osfi, eu-ai-act ×2 mirror, nist; iso-42001 ⇒
      explicit `no-source (pending-purchase)` row, never fetched); eu-ai-act
      gets an ordered candidate list `[('official', SRC_EU_OFFICIAL — the
      ELI URL https://eur-lex.europa.eu/eli/reg/2024/1689/oj/eng, which
      answered 200 / 1.5 MB to curl with a browser UA on 2026-09-12; httpx
      with the planned UA is untested — the `CROSSWALK_LIVE_FETCH=1` test is
      the first proof, and a 403 falls to the mirror and is reported as
      such), ('mirror', ART12), ('mirror', ART14)]`; `Citation.source_url`
      is NOT changed (it records what was read on RETRIEVED); `fetched_via`
      recorded. Fetcher injectable; default `httpx.Client(timeout=20,
      follow_redirects=True, headers={'User-Agent': 'field-platform-
      crosswalk/<v>'})`, https only, 8 MB cap, NO `auth_headers()` to third
      parties. Hash target: normalised text (strip script/style/meta/
      comments, collapse whitespace) — raw bytes of live pages carry nonces
      and banners; `byte_diff` reported on raw bytes; README: "content-change
      (normalised text), not semantics". First run = baseline (store hash, no
      flag, status `baseline`); a later differing hash ⇒ `StaleStore.mark
      (framework, reason=<url, sha prefixes, byte diff>)` (re-mark keeps
      `flagged_at`); unreachable ⇒ `unreachable`, NEVER `changed`. Hash store
      = third key `sources` in the stale-flags file (`_load/_persist`
      extended; a `threading.Lock` + re-load before write so a named `clear`
      is not overwritten by the timer). CLI `crosswalk regwatch check
      [--fetch]`, exit 0 unchanged / 3 changed / 2 unreachable-only. `POST
      /regwatch/check` (always 200 with per-source statuses; protected by
      authn); `GET /staleness` gains `last_check`; NO HTTP clear route ever —
      the existing `test_staleness_api_is_read_only_status` is left
      UNTOUCHED (it inspects only `staleness` paths and passes) and a NEW
      test `test_no_http_route_can_clear_staleness` asserts no route path
      contains clear/unmark, `POST /regwatch/check` with any body cannot
      remove a flag, `/staleness` stays GET-only; README row: flags can be
      SET over authenticated HTTP, never cleared. `crosswalk serve --every
      SECONDS` (`FIELD_CROSSWALK_EVERY`, compose + entrypoint default 86400;
      daemon thread, first tick after the interval, exceptions swallowed and
      logged). Tests offline: new `tests/conftest.py` autouse fixture makes
      the default httpx factory raise; one live test gated by
      `CROSSWALK_LIVE_FETCH=1`. Partial downgrade per the gates rule, named:
      live fetch from CI/GB10/Fly depends on network reachability outside
      the repo ⇒ the mechanism is Enforced (fake fetcher), the live cadence
      is Declared (`CROSSWALK_LIVE_FETCH=1` manual proof); daily egress from
      both estates to four external hosts is a Don decision (allow, or
      `FIELD_CROSSWALK_EVERY=0` on the estate and run `regwatch check
      --fetch` from rog-command). Fix stale docs: SPEC.md:13-15/20-21/
      24-26/28, api.py:37-38 (if not done in A3), pyproject:4, demo.sh:3/16,
      cli.py:195-199 help, INGESTION_LOG note, STATE.md:460-462,
      hardening.md wording that EUR-Lex "cannot be fetched" (it was the
      2026-08-09 agent's tool, not httpx). ISO/IEC 42001 stays
      pending-purchase, guard test stays; one-liner → "ISO/IEC 42001 (pending
      text purchase)". README:91 → Enforced "content-change detection";
      Declared rows: "a flagged change is material", "the daily cadence
      actually ran on the estate". *Done when:* fake-fetcher tests: baseline
      run flags nothing and records sources; changed bytes ⇒ flag with url +
      sha prefixes + byte diff; third run keeps `flagged_at`; official 200 ⇒
      `official`, official 403/timeout ⇒ mirror + `mirror`; all fetches
      raising ⇒ no flag, `unreachable` listed, exit 2; iso row `no-source`,
      zero fetch attempts; served endpoint 200 + 401 under secret; new
      no-clear test; `--every` helper ticks on a short interval and survives
      an exception; doc-drift guard test (no `TODO-CITE` in SPEC/api
      description); 42 existing tests unmodified; demo.sh exit 0 < 60 s.
- [ ] **D5 — federation: small closes.** `fedbroker add-contract --pubkey
      PEM` (PEM validated up front as Ed25519 → exit 1 on garbage; the same
      validator on `FederationContract.counterparty_pubkey_pem` so raw PUTs
      422). `CrossingRequest` gains `direction: Literal['inbound',
      'outbound'] = 'inbound'` plus `agent_id`/`manifest` as the outbound
      names (`counterparty_*` remain the inbound names; both accepted, README
      table shows which is which). Outbound mirror: OUR manifest VALID
      (`I.manifest`) → our `federated.isolated is False` (`F.isolated`) →
      counterparty ∈ OUR `allowed_peers` (`F.peer`, same lenient substring
      rule as `home_org()`) → same contract by counterparty org (one GC
      instrument covers both directions — stated) → scope/data_class ∈
      contract allowlists; the signature step is SKIPPED outbound (we cannot
      verify our own manifest with their key) — LIMITS says so; verdict
      `agent_id` = `<home_org>/<our agent>`; `context.direction` and ledger
      payload carry the direction. SDK `field_agent/federation.py`
      `FederationClient` (`FIELD_FEDERATION_URL`, AuthedClient),
      `FieldAgent.cross(counterparty_org, scope, data_class, manifest, *,
      direction='outbound', …)`, `fieldagent cross`; BLOCK ⇒ new
      `CrossingBlocked(FieldAgentError)` carrying the verdict; broker
      unreachable ⇒ `CrossingBlocked` with `verdict=None` and reason
      "federation-broker unreachable — failing closed" (no clause invented).
      The SDK asks, it never relays — README row worded so "gateway for
      traffic" is not re-implied. `FIELD_FEDERATION_URL` in compose anchor
      (A0) + entrypoint + INTEGRATION.md env table; federation-broker added
      to field-agent dev extras. Fix SPEC.md:24 (keyed contracts DO verify
      Ed25519; keyless = consistency), :14-15 (seven checks), :17, :26;
      README:3, pyproject:4, `__init__`, api.py:33 "gateway" wording →
      "crossing-decision service". *Done when:* CLI `add-contract --pubkey`
      registers the key and a following unsigned crossing BLOCKs; garbage
      PEM exit 1 / 422; outbound tests: in-contract ALLOW with direction in
      context and ledger; isolated ⇒ F.isolated; counterparty not in our
      peers ⇒ F.peer; no contract ⇒ BLOCK; out of contract scope/data_class
      ⇒ BLOCK; invalid manifest blocked before peer read; keyed contract does
      not require a signature outbound (documented asymmetry); SDK: ALLOW
      returns verdict + `federation.allow` event; BLOCK raises
      `CrossingBlocked` with the clause; broker down raises fail-closed;
      secret estate carries `x-field-auth`; `fieldagent cross` exit codes;
      12 existing tests unmodified; demo.sh exit 0 < 60 s.
- [ ] **D-gate.** governor + sentinel + gateway + registry + crosswalk +
      federation + field-core + field-agent green; CI green (compose-smoke
      now includes the gateway roundtrip); `run_demo.sh` exit 0 + tail; demo
      wall times; adversarial review; `plugin.json` → 0.1.2 (owed since
      1727de0; D1 re-vendors the example manifest) + SOURCES.md stamp +
      `verify_sync.sh` green; STATE.md incl. "needs decision by Don" (GB10
      `ANTHROPIC_API_KEY`, D1 metering proposal, crosswalk egress); summary
      → Don; STOP.

### Phase F — the "Declared, not yet enforced" slide (Don, 2026-09-12)
Don's instruction: make the five remaining components enforced instead of
declared. Mapping: perimeter → **F1** (row 2 was REWORD; new decision); kill
endpoint → **B3**; retention → **C2**, per-event signatures → **F2** (row 5
was REWORD; new decision); spend self-reported → **D1 proposal adopted** +
**D2e**, compute → **F3** (blocker, stays REWORD); attestation → **A2 + C4**,
served signing → **F4** (Don decides). F runs after D, before E (E's wording
depends on which of F1/F2/F4 land). File ownership: F1 gateway (+ sentinel
client), F2 ledger + field-core, F3 sentinel + governor (D1 proposal), F4
attest.
- [ ] **F1 — gateway as the LLM-egress enforcement point.**
      `FORCE_GATEWAY_ENFORCE=1` (default 0 = today's observer) flips
      `/v1/messages` to FAIL-CLOSED identity/authority enforcement while
      hygiene instrumentation keeps failing open — README states the
      inversion. Request headers `x-field-agent-id` (exists) + `x-field-
      token` (new; the delegation token id — the B2 "OAuth-style" pattern at
      the egress); missing either ⇒ 401 naming the headers. Before
      forwarding, the gateway calls the sentinel `POST /check {agent_id,
      token_id, action}` via a new `SentinelClient` (`FIELD_SENTINEL_URL`,
      `auth_headers()`, 5 s): `action` = `x-field-action` header when
      present (scope enforced against the manifest like any governed
      action), else the fixed action `llm.messages` (manifests that use the
      gateway list it in `delegation.scope`; templates gain a commented
      example). BLOCK ⇒ 403 `{decision, clause_id, reasons}`; ESCALATE ⇒ 403
      with `escalation: true` (an LLM call cannot pause for a human — say
      so); sentinel unreachable/5xx ⇒ 503, never forward; every refusal is a
      ledger event `gateway.refused{agent_id, clause_id}`. D2e passthrough
      requests are exempt from the check only when they carry the sentinel's
      / crosswalk's / gateway's self-manifest agent ids and valid tokens
      (they are governed agents too; provision them in compose/fly like
      `force-gateway` today) — otherwise no exemption. Optional stage 2
      (`FORCE_GATEWAY_TOOL_CHECK=1`): every `tool_use` block in the model
      response is checked as action = tool name; blocked tool calls are
      replaced by a refusal text and ledgered `gateway.tool_refused` —
      model-initiated tool intent intercepted at the egress. README rows:
      "Interception at the LLM egress — Enforced in code when
      `FORCE_GATEWAY_ENFORCE=1` AND the gateway is the mandatory egress
      (network policy is the operator's — Declared; not deployed as such on
      either estate)"; "tool execution outside LLM calls — cooperative
      (Declared)". `demo.sh` shows a killed agent refused at the egress.
      *Done when:* tests with an in-process sentinel stack: killed agent ⇒
      403 `E.kill_switch`, revoked token ⇒ 403 `D.revoked`, unregistered ⇒
      403, over cap ⇒ 403 `E.spend_cap`, throttled ⇒ 403 `E.rate_limit` with
      `retry_after_seconds`, `x-field-action` outside scope ⇒ 403 `D.scope`,
      missing headers ⇒ 401, sentinel down ⇒ 503 and NO upstream call (spy),
      enforce=0 ⇒ existing 33 tests unmodified; log-only sentinel ⇒
      forwarded with the shadow context in the ledger; stage 2: an
      out-of-scope `tool_use` is stripped and ledgered, in-scope passes
      unchanged; compose-smoke roundtrip runs with enforce=1 + a provisioned
      smoke agent; demo.sh exit 0 < 60 s.
- [ ] **F2 — per-event ledger signatures.** `FIELD_LEDGER_SIGN_KEY` (PEM path
      on the estate volume; custody is Don's — "needs deploy") ⇒ every
      appended event carries `signature` = Ed25519 over the canonical record
      INCLUDING its `hash` (hash first, sign second; `compute_event_hash`
      unchanged so pre-F2 events and every tamper test keep their meaning);
      `LedgerEvent.signature: str|None` in field-core (additive; C1 bundles
      carry it); `GET /health` reports `signing: on|off` and
      `seal_algorithm: ed25519-signed-chain` when on (enum value already in
      the schema), `sha-256-chain` when off; `FIELD_LEDGER_REQUIRE_SIGNING=1`
      refuses appends when no key is loaded (fail closed, off by default);
      `verify --pubkey` (existing flag) checks every event's signature after
      the chain walk and reports the first unsigned/invalid index; C2's
      rotation anchor uses the same key. The dogfood manifests'
      `sha-256-merkle` becomes a documented mismatch to fix on the GB10
      ("needs redeploy"). README row 40 → "Per-event signatures — Enforced in
      code when the key is set (the ledger's key; proves the ledger wrote
      it)"; "Caller authorship — Declared (per-caller keys are backlog item
      5)". *Done when:* appended events verify; editing any field of a signed
      event fails `verify --pubkey` naming the index even after the chain is
      re-linked by an attacker without the key (the anchor forgery test's
      stronger sibling); key unset ⇒ unsigned events + `signing: off`;
      require-signing refuses appends 503; wrong pubkey fails; pre-F2
      unsigned history verifies with a stated count of unsigned events; 11
      existing tests unmodified; demo.sh exit 0 < 60 s.
- [ ] **F3 — spend: platform-metered; compute stays REWORD (blocker).** Adopt
      the D1 proposal (A + B) so actions are sentinel-metered at `/check`,
      and via F1 tokens are gateway-metered for every governed LLM call.
      README row 68 → "Actions are platform-metered at /check and tokens at
      the egress — Enforced; self-reported `/spend` remains the cooperative
      path for agents outside both (Declared)". COMPUTE: the platform never
      executes agent code — CPU/GPU seconds have no observer here; the only
      implementable form is a self-reported `compute_seconds` field, i.e.
      exactly the self-reporting the slide asks to remove. Per the spec's
      gates rule this needs something outside the repo (an execution
      substrate) ⇒ stays REWORD ("drop compute"), reason recorded in E1.
      *Done when:* D1 option-A/B tests pass; F1 token-metering test (a
      forwarded request with the mock upstream lands in `/usage` for the
      header's agent); E1 row 9 carries the compute reason.
- [ ] **F4 — served attestation signing (Don decides; default OFF).**
      `FIELD_ATTEST_SIGNER` + `FIELD_ATTEST_SIGN_KEY` on the attest service:
      when both are set, `GET /pack` returns a signed pack whose `signer` is
      that name and whose provenance field `signed_via: "estate-key"` (vs
      `"cli"`) is printed in the HTML footer; unset ⇒ UNSIGNED DRAFT as in
      C4. Honesty: an unattended signature is a custodian's standing
      attestation, not a per-pack human act — README row says exactly that;
      the quarterly pack of record remains the CLI path. *Done when:* served
      pack verifies with `attest verify --pubkey`; provenance field present;
      unset ⇒ banner; tampering invalidates.
- [ ] **F-gate.** gateway + sentinel + ledger + governor + attest + field-core
      + field-agent green; CI green (compose-smoke enforce=1 roundtrip);
      `run_demo.sh` exit 0 + tail; adversarial review; STATE.md ("needs
      deploy": ledger key, attest key, enforce flag, network policy); summary
      → Don; STOP.

### Phase E — the words
- [ ] **E1 — `docs/capstone-evidence/v2-one-liners.md`.** OPEN INPUT: the
      verbatim v2 one-liners exist only as phrases quoted in the audit — Don
      drops the v2 list into `docs/capstone-evidence/v2-one-liners-source.md`
      or confirms the audit's quotes are the source; the "old" column states
      its provenance either way. Numbering = the audit's 1–12. A global line
      first: "both estates run pre-v1.2 images; every Enforced word is
      test/CI-proven; per-system estate status is Declared until redeploy"
      plus an optional Deployment-status column. Per system: old → new
      wording; Enforced / Declared split; each Enforced word names
      `path::test_name` and the commit hash; REWORD rows say why. Qualifiers
      that MUST survive: "API-key scans (file-based, heuristic)"; "at the
      agent's action boundary (SDK/@governed; cooperative perimeter)" or,
      if F1 lands, "+ intercepted at the LLM egress when the gateway is the
      mandatory egress (not deployed as such on either estate)"; DOA "when
      FIELD_DOA_ROSTER is set (unset on both estates); grantor name recorded,
      not authenticated"; "OAuth-style"; kill endpoints "allowlisted,
      best-effort; no shipped manifest declares an agent-side endpoint";
      heartbeats "for agents that check in; none do on either estate today";
      ledger "hash-chained, Ed25519-anchored; estate-level retention by
      segment rotation (mechanism; no estate rotates today — key custody
      undecided)" and, if F2 lands, "per-event ledger-signed; caller
      authorship Declared"; RACI "R/A/C/I from registry, grant, manifest with
      labeled defaults"; "Continuous (content-change detection; semantics by
      named review; live fetch verified manually, not in CI)"; "ISO/IEC
      42001 (pending text purchase)"; "crossing-decision service";
      "throttle (per-action windows over self-reported action counts —
      sentinel-metered only if the D1 proposal is adopted; governor-parseable
      periods; `session` Declared)"; "on-report metering (gateway-metered
      tokens, self-reported spend[, sentinel-metered actions — only if the
      D1 proposal is adopted and its adversarial test lands])" — or, if F3
      lands, "platform-metered actions and tokens; compute has no observer
      (dropped, reason stated)"; "org-wide when deployed as the LLM egress
      proxy (not deployed as such on either estate; platform judge traffic
      deliberately passthrough — excluded from hygiene telemetry)"; "hygiene
      telemetry rates + sycophancy drift (mechanism; judge off on both
      estates today)"; "provision → decommission, named re-attestation (name
      recorded, not authenticated)"; "quarterly (UTC-quarter window),
      Ed25519-signed by a named signer (CLI; served packs unsigned drafts
      unless F4)". *Done when:* file exists; every Enforced word cites
      `path::test_name` + commit; the E-gate script confirms each cited test
      exists and its assertion names the word; old-column provenance stated;
      the global estate-status line present.
- [ ] **E2 — README.md, ROADMAP.md, service READMEs, docs.** README 12-systems
      table gains a "One-liner" column (there is none today); ROADMAP
      one-liners to the same wording, its "209 tests" and STATE.md:303
      replaced by `python -m pytest --collect-only -q` counts; every touched
      service README table already moved in its phase — verify no `Declared
      only` row contradicts a word E1 marks Enforced; in-repo "RACI-ready"
      wording in replay README/SPEC/cli help, `integration/demo/README.md`
      and `docs/capstone-evidence/phase-3.md` aligned; `docs/IMPLEMENTATION.md`
      §8 scheduling table: lifecycle daily (`FIELD_LIFECYCLE_EVERY`),
      crosswalk daily (`FIELD_CROSSWALK_EVERY`), attest quarterly with
      `--period` + signer, `ledger rotate`/`retention` rows; ARCHITECTURE.md
      event catalog (registry.attested, lifecycle.decommissioned,
      kill.endpoint_*, ledger.*, spend.*, gateway.passthrough/refused).
      *Done when:* the column exists; counts cite the collect-only output;
      a grep over every service README finds no Declared row for an E1
      Enforced word; "RACI-ready" gone from the four in-repo locations.
- [ ] **E3 — STATE.md.** "Current phase" + "Next action" rewritten for v1.2;
      lines 122-123 (Fly "PRODUCT estate" / GB10 "burn-in (log_only)") and
      the same framing in `entrypoint.sh:10-11` and `fly.toml:1-3` →
      superseded 2026-09-08; phase gate log entries with real run tails.
      *Done when:* those three locations no longer say PRODUCT/burn-in; the
      gate log carries every phase's run_demo tail and demo wall times.
- [ ] **E4 — tasks/todo.md review section** + in-repo `tasks/lessons.md` lines
      for every correction from Don during the build. *Done when:* the Review
      section is filled; lessons.md has one line per correction.
- [ ] **E-gate.** full sweep (13 services + 2 packages), CI green,
      `run_demo.sh` exit 0, final adversarial review of `v2-one-liners.md`
      against the tests it cites, STATE.md, summary → Don.

### Decisions I made inside the plan (flag if you disagree)
1. B0 exists (resolver in field-core before B1); B3 consumes it; the
   sentinel calls the class, not the free function (spy test).
2. A3 requires `manifest` in Phase A; optionality after B0 (D4 touches the
   same file).
3. B2 parses the form manually and emits `scope` + `scope_list`.
4. B3 adds a header + path self-call guard, records unregistered check-ins,
   and adds an SDK check-in; allowlist blank by default.
5. B4 protects `retired` in kill-switch + console; lifecycle-manager gains
   spend-governor as a runtime dependency; `--name`/`--manifest-ref` flags.
6. C1 proves filtered contiguity with a hash-only spine attested by the
   signer; signing is CLI-only; the served export is unsigned.
7. C2 keeps the given path as the open segment; adds served `/rotate` and
   `/retention/check`, a rotate key (`FIELD_LEDGER_ANCHOR_KEY`, 503 without),
   legal hold place/release verbs, `FIELD_LEDGER_RETENTION_DAYS` default
   2555 as the estate policy, archive dir under `FIELD_DATA_DIR`.
8. C4: strict `--period`, scripts derive windows from `date`, served packs
   are unsigned drafts (until F4).
9. D1: per-action counting via `SpendRequest.action` + `report_spend(action)`
   now, in their own table/route so `SpendCapConfig` stays `extra=forbid`;
   sentinel metering is the proposal (A + B recommended); `session` =
   declared-unenforced.
10. D2: `FORCE_GATEWAY_URL` is new; passthrough header gated by
    `x-field-auth` on secret estates and ledgered elsewhere; count-based
    telemetry windows; the gateway's own upstream excluded from the helper.
11. D3: optional `last_used_by` column; broad patterns labeled; redaction.
12. D4: normalised-text hashing; first run = baseline; official ELI URL as a
    candidate, `source_url` unchanged; partial downgrade named.
13. D5: outbound skips the signature step; `CrossingBlocked` is an SDK error,
    not a verdict type; unreachable ⇒ no clause.
14. Minor, additive, tested expansions: A0 CI retry loop + env passthroughs;
    A2 `org` param; C1 `LedgerStore.events()` ts-compare fix (replay/attest
    tests unmodified); D2 `cot_structure_rate`, `FORCE_TELEMETRY_RETAIN`,
    `_all` route; D3 `extra='forbid'` + 1 MiB cap; D4 exit codes 0/3/2 + 8 MB
    cap.
15. Phase F added on Don's 2026-09-12 instruction; F1/F2/F4 are new
    decisions beyond the table; F3 keeps the compute REWORD as a blocker.

### Decisions for Don at approval
Q1 branch strategy (commits on `main`, push per gate) — yes/no. Q2 merge
df774fe + commit or discard the ADR working-tree edit before P2. Q3
`FIELD_LEDGER_RETENTION_DAYS` default 2555 in compose/fly. Q4 served
`/rotate` with `FIELD_LEDGER_ANCHOR_KEY` (503 without) vs CLI-only rotation.
Q5 D1 metering proposal: adopt A + B now (recommended) / A only / defer.
Q6 D2 passthrough gating as written. Q7 crosswalk daily egress from the
estates: allow, or `FIELD_CROSSWALK_EVERY=0` + manual runs. Q8 GB10
`ANTHROPIC_API_KEY` after `--mock` removal. Q9 Phase F: F1 stage 2 in or
out; F2 `FIELD_LEDGER_REQUIRE_SIGNING` default; F3 compute stays REWORD;
F4 on or off. Q10 E1 source: drop the v2 list into the repo, or accept the
audit's quotes. Q11 B4 `retired` protection in kill-switch + console.
Q12 B3 SDK check-in in Phase B.

### Review
(filled at the end of each phase)
