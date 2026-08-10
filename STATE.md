# STATE — FIELD Platform

> Update before ending any session. Assume many sessions.

## Current phase
Hardening round 2 + **ops-console** — complete (2026-08-09). 13 services
(12 governance systems + the dashboard), 168 tests green.

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

## Next action (remaining backlog, in rough priority)
1. Push repo to a GitHub remote → CI workflow runs for real (matrix +
   x86_64 compose smoke).
2. Manual EUR-Lex cross-check of EU AI Act Art. 12 + 14 (fetch tooling
   can't — human with a browser can); purchase + ingest ISO/IEC 42001.
3. Schedule `ledger anchor` (Task Scheduler/cron) with the anchor file
   shipped off-box; evaluate OpenTimestamps publication of anchor records.
4. Signing-key rotation/revocation; per-caller identity; TLS via proxy.
5. Enhancements: sentinel verdict-write durability, ledger read index,
   `attested_at` for lifecycle, gateway streaming, telemetry persistence,
   ops-console pagination/push, quarterly pack archive convention.
6. Capstone packaging: record the demo video (run_demo.sh + ops-console
   demo.sh make the visual spine).

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
