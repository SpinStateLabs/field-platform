# STATE — FIELD Platform

> Update before ending any session. Assume many sessions.

## Productionization step 1 — single-port compose (2026-08-29)
The compose stack now publishes ONE host port: a Caddy reverse proxy
(`integration/demo/Caddyfile`, caddy:2-alpine service in
docker-compose.yml) path-routes /registry /ledger /delegation /sentinel
/killswitch /governor /replay /gateway /federation, with the ops-console
at the proxy ROOT (its static shell fetches root-absolute /api/* — it
cannot live under a prefix). handle_path strips prefixes so every app
still sees root paths (/health stays in authn OPEN_PATHS) — ZERO Python
changes. Per-service host ports removed from both compose files; GB10
override collapses 18001-18011 → 18080. CI compose-smoke rewritten to go
through the proxy (health loop + governed smoke on :8080/<prefix>).
Design adversarially verified pre-change by a 6-agent audit workflow
(httpx base_url path-merge and proxy prefix-strip verified empirically on
the project venv; the CI-job breakage was caught by the verifier and
fixed as part of the change). Host-side callers against compose must set
FIELD_*_URL to http://localhost:8080/<prefix> (documented in
.env.example, IMPLEMENTATION.md §3, integration/demo/README.md). Local
no-docker path (run_demo.sh, demo.sh, 800x defaults) UNCHANGED. Swagger
/docs 404s behind stripped prefixes (root-absolute /openapi.json) —
cosmetic, noted in .env.example; --root-path plumbing is the known fix if
ever needed. GB10 cutover NOT applied (operational boundary: GB10 changes
run on the GB10) — sequence it before starting or after finishing the
burn-in window, never mid-window (recreating the sentinel container
resets the 2-week clock; warning now in the gb10 override header).
Audit also confirmed (2026-08-29, verified twice): the ADR series is
EXACTLY the 3 packs (02/07/10 — external UWaterloo "Initiative" numbers,
not a sequence with gaps; packs 01/03-06/08-09 never existed anywhere in
the tree); all three are code-complete with suites re-run green during
the audit (sentinel 59/59, gateway 33/33, crosswalk 42/42); Netlify
CANNOT host the API tier (re-confirmed vs current Netlify docs — static
tier only: site-deploy/ is drag-drop ready); remaining-work sweep
produced 53 items (see Next action + Open questions; full list in the
session artifact).

## Current phase
**Force-Field v1.1 ADR build — in progress (2026-08-29).** Extending
field-platform (user-confirmed) to add the ADR delta on the existing
deterministic services. Authoritative design: `docs/adr/` (ADR 02 Sentinel,
07 Crosswalk, 10 Gateway). Brief workflow: `tasks/todo.md` + `tasks/lessons.md`;
plan at `~/.claude/plans/twinkly-painting-elephant.md` (approved). Build order
Sentinel → Gateway → Crosswalk. Safety ordering: log-only first.

**Sentinel S1 — DONE (log-only mode).** `FIELD_SENTINEL_MODE=log_only|enforce`;
served estate defaults to **log_only** (safe-by-default), one env var flips the
whole estate. In log_only, `/check` returns ALLOW and shadow-ledgers the true
verdict as `conformance.shadow_block|shadow_escalate` (with `would_block`
clause). Engine constructor defaults ENFORCE (existing unit tests unchanged);
demos + compose smoke set `FIELD_SENTINEL_MODE=enforce`. `mode.py` added;
`engine._verdict` mode-aware; `/health` reports mode. Sentinel suite **20/20**;
enforce demo real-run confirms blocking + chain intact.

**Sentinel S2 — DONE (seeded suite + scorecard, 2026-08-29).** Plan-mode pass
approved (`~/.claude/plans/frolicking-riding-bear.md`), design adversarially
hardened by a 3-agent critique before approval. `routing.py`
(needs_semantic_judgment — measurement-only; S3 attaches the judge here),
`seeded.py` (deterministic hermetic 100-action corpus, dedicated seed-agent,
5 violation categories incl. ledger-unreachable — honestly renamed from
"missing-ledger-write"), `measure.py` (log-only REQUIRED, refuses enforce;
catch from in-band `context.would_be`, valid while ledger down), `sentinel
score` CLI (exit 3 on gate fail; `--ledger-down-cmd` for owned stacks).
Metrics honest by design: gated catch is clause+decision-matched (wrong-reason
refusals don't count); false-block gated on structural conforming only, with
the combined rate incl. semantic gap reported at equal prominence (11.7% —
S3's job); routing coverage labeled mix-driven, economics *s* pending live
telemetry; tokens/judgment 0 sourced. Real served run (log_only default
verified): **gates PASS 40/40 catch, 0/53 false-block**; artifact committed at
docs/capstone-evidence/sentinel-scorecard-s2.md|.json. Sentinel suite **32/32**
(4 S1-backfill tests pin log-only+ledger-down fail-open, genuine-ALLOW
unshadowed, escalate-shadow negatives, resolve_mode fallback — all found by
the adversarial audit; documented in README LIMITS + .env.example).
score_demo.sh real run 82 s (500 localhost HTTP round-trips on Windows; <60 s
target relaxed to <2 min, noted). RAISED S2-R (todo.md): attestation-reporter
+ crosswalk are shadow-blind — a log-only estate's board pack reads 100%
conformant while violations shadow-ledger; fix before any burn-in. Next: S3
semantic judge (flagged, mockable), S4 self-manifest + tenant isolation.

**S2-R — DONE (shadow-aware reporting, 2026-08-29, user-approved).** Board
pack now shows shadow_block/shadow_escalate as their own labeled rows
("log-only, not enforced") and counts them in the conformance-rate
denominator (metric renamed "Conformance rate (ALLOW / all verdicts incl.
shadow)") — a log-only estate can no longer read 100% conformant
(adversarial test: 3 allows + 3 shadow verdicts → 37.5%, note names the
shadow count). Crosswalk FC-E-03 evidence reads "N enforced + S shadow
(log-only) escalation event(s)" — shadow proves the trigger fires, not that
a human was paused. run_demo.sh board-pack scene updated to the new metric
name; full integration demo real-run green (exit 0; enforce-mode rate 71.4%
unchanged — shadow terms 0, backward compatible). attestation 7/7,
crosswalk 10/10. The burn-in evidence path is now shadow-aware.

**Sentinel S3 — DONE (semantic judge, flagged + mockable, 2026-08-29;
plan auto-approved by user directive).** `FIELD_SENTINEL_JUDGE=off|mock|
anthropic`, DEFAULT OFF — judge-off behavior is S2-identical (proved twice:
existing suite unmodified + real score_demo re-run, gates PASS unchanged,
89 s). `judge.py`: pinned JUDGE_MODEL_DEFAULT=claude-sonnet-5 (env override,
recorded in every verdict + sentinel.judge ledger telemetry), deterministic
injection_screen (pattern list + length cap — README LIMITS: evolving, a
pass is necessary not sufficient), MockJudgeClient (records calls),
AnthropicJudgeClient (key from env only, strict-JSON rubric, action marked
DATA; # pragma: no cover — Declared-untested without keys). Engine step 5:
non-member + routing predicate ⇒ judge against EFFECTIVE scope
(token∩manifest — narrower grant wins; delegation mint does NOT validate
scope⊆manifest, verified). Fail-to-escalate D.semantic (new field-core
clause) on ALL of: screen trip, governor unreachable, no sentinel cap
(refuses unmetered judgments — /usage 404s uncapped agents), budget BLOCK
(structural-only throttle), judge error, unparseable/uncertain, below floor
(FIELD_JUDGE_CONFIDENCE_FLOOR=0.8), metering failure. Judge pass does NOT
bypass remaining checks; log-only shadows judge verdicts. Golden set (mock
rules from seed labels): AC 7/7 ALLOW (semantic gap closes), AV 8/8 BLOCK
D.scope, SB 8/8 + OK 53/53 never consult the judge. Sentinel **52/52**
(20 new), field-core 58/58. HONESTY LINE: mock tests prove control flow
only; semantic understanding quality is Declared until live golden evals
with the pinned model. Next: S4 self-manifest + tenant isolation (also
completes the judge's spend story: sentinel's own manifest declares the
cap the governor meters).

**Sentinel S4 — DONE (self-manifest + tenant isolation, 2026-08-29; plan
auto-approved by user directive). ADR 02 SENTINEL TRACK COMPLETE (S1–S4).**
Who guards the guard, as tested properties. `self_manifest.yaml` ships as
package data (inspect: `sentinel self-manifest`, exit 1 if invalid — real
run exit 0): principal "Founder & CTO, Spin State Labs"; delegation scope
verb-restricted to read/evaluate/append/invoke (test enforces — read-only
grounding); enforcement.spend_cap USD 5/daily IS the S3 judge budget,
applied via the EXISTING `governor set-cap conformance-sentinel
--from-manifest` flow (test: manifest-derived cap → judged call ALLOWED and
metered, /usage shows tokens). Tenant isolation TESTED per ADR 3: resolver
spy proves check(A) resolves only A's manifest_ref even when A's token
carries an action only B's manifest grants (BLOCK D.scope, no leak); judge
path proves the mock's scope ⊆ A's manifest. No-self-modification enforced
concretely: API surface has zero PUT/PATCH/DELETE routes and POST only at
/check; full check battery leaves manifest bytes identical. OS-level
immutability Declared (mount manifests read-only in deployment — LIMITS).
Sentinel **59/59** (7 new). Sentinel gate to v0.2 enforce-default remains
the LIVE burn-in (≥2 weeks log-only on real agents). Next per build order:
System 2 — FORCE Gateway delta (own plan-mode pass), System 3 — Crosswalk
delta; ISO/EUR-Lex backlog unchanged.

**System 2 — FORCE Gateway delta — DONE (ADR 10, 2026-08-29; plan
auto-approved by user directive).** The observer that fails OPEN — the
deliberate mirror of the Sentinel. `hygiene_judge.py`: sampled semantic
judge, FORCE_HYGIENE_JUDGE=off|mock|anthropic DEFAULT OFF (unrecognized→off),
pinned cheap class claude-haiku-4-5-20251001, rubric hygiene-v1, DETERMINISTIC
1-in-N sampling (FORCE_GATEWAY_SAMPLE_EVERY=10, 0=off — not random, on
purpose). `drift.py`: per-route (=preset) count-based windows (5), baseline =
first 2 windows, band ±0.15; alert ONLY on two consecutive out-of-band
windows, one alert per episode, re-arm on recovery; judge-model/rubric change
resets the baseline; `gateway.drift_alert` ledgered. Fail-open in api.py:
instrumentation faults and overhead > FORCE_GATEWAY_LATENCY_BUDGET_MS (250)
enter bypass — traffic forwards UNINSTRUMENTED (no injection, proved by
captured upstream bodies) for a cooldown (10), `gateway.bypass` ledgered on
entry, every gap in /telemetry `coverage` — never silent. Judge separately
spend-gated on the Gateway's OWN cap (agent force-gateway): no
governor/404/BLOCK/error skips the judgment only, structural telemetry
continues, `judge_bypassed[reason]` counted; judged samples metered via
/usage. Gateway self-manifest (S4 pattern): CTO owner, observer-verb scope
(test-enforced), USD 5/daily judge budget via `governor set-cap
force-gateway --from-manifest`; `forcegw self-manifest` real run exit 0.
Gateway **33/33** (20 new; existing 13 unmodified). HONESTY: mock proves
control flow; judge scoring quality Declared pending ADR 10's quarterly
human calibration; telemetry/drift/bypass state is in-memory and
session-scoped until the telemetry-persistence backlog item (LIMITS).
Next: System 3 — Compliance Crosswalk delta (ADR 07, own plan-mode pass).

**System 3 — Crosswalk delta — DONE (ADR 07, 2026-08-29; plan auto-approved;
built by 3 PARALLEL agents on disjoint modules per user request, all green
first pass). v1.1 ADR BUILD CODE-COMPLETE (Sentinel S1–S4 + Gateway +
Crosswalk).** Everything bends against a signed false assurance.
`suggestions.py`: CROSSWALK_SUGGEST=off|mock|anthropic DEFAULT OFF; precision
floor 0.8 — below-floor/error renders "unmapped — review required" (a
first-class conservative output), NEVER a candidate; a model validator
refuses half-mapped candidates; authored CONTROLS matrix is the sole source
of truth (immutability test); every entry carries "SUGGESTION ONLY" +
rubric suggest-v1 + pinned claude-sonnet-5; anthropic path refuses without a
governor cap (self-manifest declares USD 5/daily). `evidence_pack.py`:
three-part citations (clause · control · reference + retrieved 2026-08-08)
on every row; pending-text/pending-purchase rendered as exactly that; NO
pack without a named signer; verbatim "Signature is the action — this
system never asserts compliance; a named human signs, or nothing ships."
(word-discipline test: 'complian*' appears only in that sentence).
`staleness.py`: CORPUS_VERSION=corpus-2026-08-08 pinned to
mapping.RETRIEVED; StaleStore at $FIELD_DATA_DIR/crosswalk_stale_flags.json;
stale flag HARD-BLOCKS pack generation (StalePackError, no override
parameter exists) until `regwatch clear --reviewed-by NAME` (named, logged
with history); stale window length reported; affected_controls listed.
CLI: crosswalk suggest|pack|regwatch(status|set-stale|clear)|self-manifest;
GET /staleness read-only. Crosswalk **42/42** (10 existing unmodified + 32
new). REAL RUN captured: self-manifest exit 0 → set-stale eu-ai-act → pack
BLOCKED exit 3 (names FC-E-01/03, FC-I-01, FC-L-01/02; "there is no
override") → clear by named reviewer → pack exit 0 (36 citation rows).
HONESTY: reg-change DETECTION is operator-fed in v0.1 (EUR-Lex fetch limits
on record) — the enforcement is code, the cadence is a process commitment;
suggestion precision Declared until human review data. REMAINING (not
code): 2-week live log-only burn-in (calendar), manual EUR-Lex cross-check
+ ISO/IEC 42001 purchase (human), telemetry persistence + key rotation
(backlog enhancements, own passes).

**GB10 DEPLOYMENT — LIVE (2026-08-29, v1.1 code 806d8c0 + override
3c1eaf3).** Full 10-service compose stack up on the DGX Spark from
~/field-platform via `docker compose -f integration/demo/docker-compose.yml
-f integration/demo/docker-compose.gb10.yml up -d --build`. The GB10 hosts
other live workloads on 8000-8010 (open-webui tool servers, spintrader) —
FIELD publishes on **1800x** via the committed gb10 override (container
ports/inter-service URLs unchanged). VERIFIED: all 10 /health OK; sentinel
reports mode=enforce (compose anchor) + judge=off; gateway reports
judge=off sample_every=10; real governed smoke → BLOCK R.unregistered,
verdict ledgered, chain verify ok at length 265 (field-data volume
persists prior runs). compliance-crosswalk is CLI/offline tooling — not a
composed service. Stop with: `docker compose ... down` (same two -f files).
Locally nothing serves persistently by design: editable venv installs +
on-demand demo stacks (verified importable post-806d8c0).

## field-agent client SDK (2026-08-29) — DONE
The last mile: `packages/field-agent` puts a real agent under governance in
a few lines. **209 tests green** (17 new; also un-time-bombed the
lifecycle/attestation test fixtures, which had gone red on date drift —
frozen NOW vs real service clocks).
- FieldAgent facade: `check`/`@governed` (re-exports the sentinel's own
  `governed.py` — identity-tested, no verdict logic duplicated),
  `report_usage[_from]`/`report_spend` (STRICT: failure raises; no-cap 404
  ⇒ NoSpendCapError), `ensure_alive` (killed/unknown/unreachable all halt —
  HeartbeatUnreachable ⊂ AgentKilled), per-request x-field-auth
  (AuthedClient), operator-side bootstrap.register/mint kept OFF the facade,
  `fieldagent` CLI (check exits 0/1/2 = ALLOW/BLOCK/ESCALATE).
- Client, not authority: zero new power; cooperative perimeter stated in
  README (exact Enforced-vs-Declared), SPEC, docs/INTEGRATION.md.
- demo.sh: six services, enforce mode, 28 s, passes with and without
  FIELD_SHARED_SECRET.
- integration demo converted to the SDK: per-draft usage metering, rogue
  Opus flagged, new scene 6b (real kill ⇒ SDK halts ⇒ revive); 96%-escalation
  story intact. Real run log: docs/capstone-evidence/field-agent-run.log
  (+ narrative field-agent.md). NOTE: future capstone-video regens will show
  the new scene 6b and usage lines.
- CI + IMPLEMENTATION.md wired (`pip install --no-deps -e
  packages/field-agent`; conftest test group). --no-deps is mandatory:
  conformance-sentinel is not on PyPI. v0.2 idea on record: promote
  governed.py into field-core to drop the service dep.
- examples/ (d066218): copy-paste agent_template.py + per-hook samples +
  operator bootstrap + raw-REST curl equivalent (REST is the whole
  interface; every service serves OpenAPI at :port/docs);
  examples/run_all.sh verified ~26 s against an ephemeral enforce stack.

## field-agent Claude Code plugin (2026-08-29) — DONE
`plugins/field-agent/` packages the SDK integration surface for Claude
Code: skill (`SKILL.md` honesty rules + `integration.md` hook API/env/
troubleshooting + `rest-api.md` five fail-closed rules for non-Python +
`checklist.md` A–F compliance rubric), `/field-agent` command
(new | verify | bootstrap | rest | env), and `templates/` vendored
BYTE-FOR-BYTE from the monorepo (agent_template.py, 04_bootstrap →
bootstrap_operator.py, 05_rest → rest_api.sh, default manifest + schema +
resolved invoicing-agent example) with provenance stamped in
`templates/SOURCES.md` (base 4df1cfc) and a drift gate
`plugins/field-agent/verify_sync.sh` (run green at vendoring; NOT yet in
CI — candidate workflow step). Repo-root `.claude-plugin/marketplace.json`
makes the repo installable: `claude plugin marketplace add
SpinStateLabs/field-platform` → `claude plugin install
field-agent@field-platform`. Boundary kept: design-time manifests stay the
Force-Field repo's `field` plugin; this plugin is build-time code
integration (they compose). Honesty line carried into the plugin: client-
not-authority, cooperative perimeter, Enforced-vs-Declared, never
"Force Field Framework".

**Plugin verified live (same day, now v0.1.1).** Install smoke test PASSED
end-to-end (marketplace add from GitHub, install, enabled user-scope); it
caught fresh-Windows-clone CRLF breaking `.sh` templates on Linux/WSL —
fixed by `.gitattributes` `*.sh text eol=lf` (14eadc3), reinstall verified
LF. `claude plugin validate` fix: `repository` must be a STRING (a92bbe4).
`/field-agent help` + `new` exercised live: scaffolded agent + manifest,
`field validate` VALID, module imports vs the real SDK. Dogfood finding
fixed at 0.1.1 (e38ed2c): agent_template.py docstring now states the
cooperative-perimeter limit (checklist F1). LESSON: bump the plugin
version whenever vendored templates change — same-version `plugin update`
delivers nothing. Same repository-string bug fixed in the Force-Field
repo's field/force plugins (v1.0.1, GitHub main ca47487; that repo's
local-vs-origin divergence was reconciled separately at ef17048 — see the
Force-Field repo).

## Prior phase
Hardening round 2 + **ops-console** — complete (2026-08-09). 13 services
(12 governance systems + the dashboard), 168 tests green; token-cost governance
2026-08-11 (185 tests).

## Token-cost governance (2026-08-11) — DONE
Agents report token usage; FIELD prices it from the model used and flags
rogue agents. 185 tests green.
- field_core.pricing: price book (Anthropic public list, dated+sourced,
  overridable via FIELD_PRICE_BOOK) + exact integer cost (1e-7 USD units;
  unpriced model -> None, never guessed).
- spend-governor: /usage (report model+tokens), /usage/{agent} breakdown,
  /policies/{agent} (allowed_models + token_rate_limit). Token cost folds
  into the SAME dollar cap. Rogue signals rogue_model / rogue_burst /
  unpriced -> ledger events + escalations. CLI: governor usage | set-policy.
- force-gateway reports model+tokens to /usage (fallback /spend on 404).
- ops-console: "Token Usage & Cost - Rogue Monitor" panel. VERIFIED LIVE:
  invoicing-agent flagged ROGUE burning Opus off its Haiku allow-list.
- Demo: services/spend-governor/demo_usage.sh.
NOTE: services are NOT persistent daemons — run demo.sh / compose to bring a
stack up; nothing runs between sessions.

## Capstone video (2026-08-10) — DONE
Full 5-scene film recorded and committed: integration/video/out/capstone.mp4
(2:24, 1080p30). Honesty contract held: every terminal command executed,
every output line verbatim; Scene 3 driven against the LIVE ops-console via
Playwright (real D.scope harness verdict + real console kill on the ledger).
Regenerate: record_scene4.py, record_scenes.py (scene1/2/3/5 + stitch),
capture_scene3.py (needs the console stack up on :8011). Per-scene mp4s and
browser shots are gitignored; capstone.mp4 + scene4.mp4 are committed.
The ONLY remaining backlog items are non-engineering: manual EUR-Lex
read-through of the two EU AI Act articles, and the ISO/IEC 42001 purchase.

## Round-2 summary (2026-08-09)
- **ops-console (:8011)** — the dashboard for harnessing agents: agents
  (kill/drill/revive), tokens (revoke), spend escalation queue (resolve),
  live ledger tail + integrity badge, sentinel dry-run harness. Client-not-
  authority: every mutation proxies the owning service; operator name
  mandatory; unavailable-not-faked aggregation; authn split (shell open,
  /api locked). VERIFIED LIVE in browser: staged 3-agent fleet, harness
  returned BLOCK [D.scope] through the real page. `console serve`;
  demo.sh leaves the stack up for exploration; in compose.
- **agent-registry → ledger**: registry.registered / status_changed /
  updated events (best-effort, env-wired) — gap closed.
- **sealed-ledger anchoring**: `ledger anchor` + `verify --anchors
  [--pubkey]`; adversarial test proves a self-consistent full-history
  forgery passes verify_chain but fails anchors; signed anchors make the
  anchor file tamper-evident. Anchor file must live OFF-BOX; public-chain
  publication (OpenTimestamps-style) is the documented next step.
- **CI workflow** written (.github/workflows/ci.yml: py 3.11–3.14 matrix +
  x86_64 compose smoke) — UNTESTED until the repo gets a GitHub remote.
- EUR-Lex cross-check attempted: CELEX doc exceeds fetch tooling (truncates
  in recitals) — noted in INGESTION_LOG; manual check still required.

## Hardening summary
- OQ-1 RESOLVED: FIELD_SHARED_SECRET x-field-auth middleware on all 10
  APIs (/health open); headers attached at every internal client/CLI call
  site; off by default. TLS still a fronting-proxy concern.
- Federation signing: Ed25519 (field_core.signing, cryptography dep);
  keyed contracts require valid manifest signatures; fedbroker keygen|sign.
  Key rotation protocol still open.
- OQ-5 RESOLVED: compose verified on GB10 (DGX Spark aarch64, Docker 29):
  9 services healthy, governed smoke flow correct, ~4 min. Dockerfile
  defect found+fixed (federation-broker missing from pip list). Netlify
  rejected (static/serverless — cannot run containers). x86_64 run pending.
  GB10 staging: /home/spinner/field-platform-verify/ (images left in place).
- OQ-2 RESOLVED (3 of 4): grounded Citation model; EU AI Act Art. 12 +
  14(4)(e) stop-button, NIST AI RMF (GOVERN 1.6/1.7/2.1/2.3/6.1/6.2,
  MANAGE 2.4, MEASURE 3.1), OSFI E-23 2027 Principles 1.1/1.2/2.1/3.1/3.6
  — all verified 2026-08-08 with source URLs in INGESTION_LOG. ISO 42001
  pending-purchase (guard-enforced). EUR-Lex cross-check flagged.

## Last completed milestone
Phase 4 gate passed (2026-08-08). Shipped to DoD:
- **federation-broker** (:8010) — six-step crossing decision (manifest
  VALID → not isolated → names us → contract → scope → data class);
  federation.allow|block ledger events; FIELD_ORG_NAME sets home org;
  LIMITS: manifests unsigned, contracts are the real gate. 7 tests.
- **lifecycle-manager** (CLI job, exit 3 on findings) — expiring
  authorities (30 d), re-attestation due (90 d), orphans vs owners.csv;
  ledger escalations; --auto-kill-orphans NEVER default (adversarial
  test), idempotent kills via kill-switch. 6 tests.
- **attestation-reporter** (CLI `attest render`) — board pack JSON+HTML+PDF
  (PDF via headless msedge VERIFIED here — OQ-3 resolved best-effort);
  Metric model enforces no-number-without-source; unavailable ≠ zero;
  tampered chain leads the pack as BROKEN. 6 tests. Fixed on review: fetch
  helper collapsed lists before transforms (revoked count was wrong).
- **run_demo.sh completes all 8 steps** (~23 s) ending with the board pack.
- Platform totals: **139 tests green**, 12 systems + field-core, 16 commits.
- Evidence: docs/capstone-evidence/phase-0..4.md.

Phase 3 summary (context) — shipped earlier same day:
- **incident-replay** (:8007) — deterministic post-mortems (who granted
  authority / what ran / which clause failed), ledger-verify gate brands
  tampered trails INTEGRITY FAILED, RACI table, markdown output. 5 tests.
- **compliance-crosswalk** (:8008) — 10 FC-* controls, ALL citations
  TODO-CITE-AFTER-INGESTION (guard test enforces; never fabricate),
  declared-vs-evidenced coverage matrix with live evidence collector. 7 tests.
- **force-gateway** (:8009) — Anthropic-shape proxy, FORCE presets composed
  verbatim from vendored plugin protocol.md, system-prompt-preserving
  injection, labeled regex telemetry, governor token spend, deterministic
  mock upstream (no keys needed). 13 tests.
- **integration demo** — run_demo.sh VERIFIED (~21 s, local processes):
  validate → register → cap-from-manifest → mint → 4 drafts allowed +
  metered → 5th ESCALATE E.spend_threshold → transfer-funds BLOCK D.scope →
  kill drill 52.84 ms → post-mortem → 15-event chain intact.
  docker-compose.yml + Dockerfile written but UNTESTED (no docker here).
- Platform test total: **120 passing**.
- Evidence: docs/capstone-evidence/phase-0..3.md.

Phase 2 summary (context): spend-governor (:8006, integer-cents metering,
escalate-before-cap), kill-switch (:8005, act-first halt + drills),
conformance-sentinel (:8004, 8-step /check + @governed decorator).
- **spend-governor** (:8006) — integer-cents metering, caps from manifest
  spend_cap, 80% threshold ESCALATE to human queue before cap BLOCK,
  /caps /spend /status /escalations(+resolve). Demo ~10 s.
- **kill-switch** (:8005) — /kill/{agent}, /kill/domain/{d}, /revive,
  /heartbeat (unknown ⇒ killed=true), /drill with ms report (drill run:
  ~59 ms total). Act-first: kill survives ledger outage. CLI `killswitch`
  (avoids shell builtin). Demo ~11 s.
- **conformance-sentinel** (:8004) — /check → ALLOW/BLOCK/ESCALATE + clause
  id; 8-step sequence (ledger reachability, registry/kill, manifest
  validity via mtime-cached field validate, token introspection, scope
  token∩manifest, irreversible policy, triggers, spend state); all verdicts
  are ledger events; `@governed` decorator + `Governor.check`. Demo boots
  all six services ~21 s.
- field-core: shared HTTP clients at `field_core.clients` (registry get/
  list/set_status, ledger append; lazy httpx); new clause `I.manifest`.
- Platform test total: **95 passing** (41+6+7+8+10+8+15).
- Evidence: docs/capstone-evidence/phase-0.md, phase-1.md, phase-2.md.

## Phase 1 summary (for context)
Spine: sealed-ledger (:8002, hash-chained JSONL, tamper detection),
agent-registry (:8001, SQLite CRUD + /discover shadow-agent scanner),
delegation-authority (:8003, ledger-first fail-closed mint/revoke,
/introspect).

## Remote (verified 2026-08-09)
- `gb10` → `gx10:git/field-platform.git` (bare repo on the DGX Spark,
  spinner@10.0.0.62 via ssh host `gx10`; HEAD set to main). `git push gb10
  main` from this machine works; working clone on the GB10 at
  `~/field-platform` for compose runs (`git -C ~/field-platform pull`).
- `origin` → https://github.com/SpinStateLabs/field-platform (private,
  created 2026-08-09). CI VERIFIED GREEN on run #2: py 3.11/3.12/3.13/3.14
  matrix + x86_64 compose smoke (build, 9 healthy services, governed flow
  BLOCK I.manifest, ledger verify ok). Run #1 failure was a workflow bug
  (bare pytest vs python -m pytest for tests.conftest imports) — fixed in
  31db5c3. Both architectures now covered: GB10 aarch64 + GH x86_64.

## Environment facts (verified this machine)
- Python 3.12 NOT installed; available 3.14 (default), 3.11, 3.9.
  Decision: `requires-python >=3.11`, develop on 3.14.2.
- Venv OUTSIDE Google Drive (sync churn): `C:\Users\donal\.venvs\field-platform`.
  Git Bash: `~/.venvs/field-platform/Scripts/python.exe`. Installed editable:
  field-core, sealed-ledger, agent-registry, delegation-authority (+deps
  fastapi/uvicorn/httpx/pytest).
- Windows console is cp1252 — every CLI forces UTF-8 stdout; write files via
  CLI flags (`--out`), not shell redirects.
- SQLite on Windows: brief file-lock lag after killing a serving process
  (delegation demo sleeps 1 s before temp cleanup).
- Source templates/schema vendored verbatim from local
  `../Force-Field-with-git/Force-Field/plugins/field/skills/field/`.
  Audited 2026-08-29 against the reconciled Force-Field canonical
  (merge ef17048): field-core manifest-schema.json + all 4 templates AND
  the field-agent SDK default template are byte-identical (mod CRLF) —
  origin's bf03d9f fixes were already in the vendored lineage; nothing
  stale, no re-vendor needed.

## Next action (remaining backlog, in rough priority)
(Items "push to GitHub" and "record capstone video" removed 2026-08-29 —
both verified done earlier in this file: Remote section 2026-08-09,
Capstone video section 2026-08-10.)
1. Deployment (private first): GB10 proxy cutover (on the GB10, sequenced
   around the burn-in window) + Cloudflare Tunnel or Tailscale Serve in
   front of :18080 with FIELD_SHARED_SECRET ON. Netlify gets ONLY the
   static tier (site-deploy/ is ready; docs + capstone evidence optional).
2. Start the 2-week log-only burn-in on real agents (calendar gate to
   v0.2 enforce-default) + 30-day false-block window.
3. Manual EUR-Lex cross-check of EU AI Act Art. 12 + 14 (fetch tooling
   can't — human with a browser can); purchase + ingest ISO/IEC 42001.
4. Schedule `ledger anchor` (Task Scheduler/cron) with the anchor file
   shipped off-box; evaluate OpenTimestamps publication of anchor records.
5. Signing-key rotation/revocation; per-caller identity; TLS via proxy
   (the compose proxy exists now; TLS/identity land at the tunnel/edge).
6. Enhancements: sentinel verdict-write durability, ledger read index,
   `attested_at` for lifecycle, gateway streaming, telemetry persistence,
   ops-console pagination/push, quarterly pack archive convention,
   verify_sync.sh into CI.

## Open questions
- OQ-1: inter-service authn deferred — localhost trust in v0.1, stated in
  every LIMITS. Revisit before any non-local deployment.
- OQ-2: compliance-crosswalk must ingest real regulation texts in a later
  session (OSFI E-23, EU AI Act, ISO 42001, NIST AI RMF) — never fabricate.
- OQ-3: attestation-reporter PDF path on Windows — candidate: HTML +
  headless-Chromium print. Decide in Phase 4.
- OQ-4: RESOLVED in Phase 2 — sentinel resolves registry `manifest_ref`
  with mtime-cached field-core validation; invalid ⇒ I.manifest BLOCK.
- OQ-5: docker not installed on this machine; integration compose files
  are written but UNTESTED — verify on a docker-equipped machine or CI.
  run_demo.sh (local processes) is the verified demo path.

## Phase gate log
- 2026-08-08 — Phase 0 complete: field-core DoD met, 41/41 tests green.
- 2026-08-08 — Phase 1 complete: spine DoD met, 62/62 platform tests green.
- 2026-08-08 — Phase 2 complete: enforcement DoD met, 95/95 tests green.
- 2026-08-08 — Phase 3 complete: intelligence + integration demo, 120/120
  tests green; run_demo.sh verified ~21 s.
- 2026-08-08 — Phase 4 complete: ALL 12 SYSTEMS SHIPPED. 139/139 tests
  green; run_demo.sh executes all 8 scenario steps (~23 s) ending with the
  board pack; OQ-3 resolved (headless-Edge PDF verified); OQ-4 resolved
  earlier. Open: OQ-1 authn, OQ-2 ingestion, OQ-5 compose verification.
- 2026-08-08 — Hardening pass complete: OQ-1 (authn), OQ-5 (compose
  verified on GB10 aarch64, Dockerfile defect found+fixed), OQ-2 (grounded
  citations for EU AI Act / NIST AI RMF / OSFI E-23; ISO pending-purchase),
  Ed25519 manifest signing. 156/156 tests green.
