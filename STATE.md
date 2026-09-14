# STATE — FIELD Platform

> Update before ending any session. Assume many sessions.

## Enforcement Gate (`field` plugin 1.1.0) — field-core lockstep (2026-09-12) — DONE
Force-Field's `field` plugin 1.1.0 (marketplace 1.2.0; Force-Field#1 →
d14ffcc) ships a Claude Code `PreToolUse` hook (`plugins/field/hooks/`)
that enforces E1 kill switch, E2 protected paths, E3 deny patterns, E4
tool-call budget and L a sha-256 hash-chained ledger from
`./field-manifest.yaml` (details: Force-Field CHANGELOG 1.1.0). It reuses
the existing vocabulary (`kill_switch.method: file`, `rate_limits
{action: tool_call, period: session}`, path-like `ledger.store`) and adds
two OPTIONAL keys — `enforcement.irreversible_actions.deny_patterns[]`,
`enforcement.protected_paths[]` — plus `seal_algorithm: sha-256-chain`.
field-core's Pydantic mirror is `extra="forbid"`, so without lockstep any
manifest using the new keys or `sha-256-chain` validates INVALID here
(the pre-existing vocabulary alone stayed VALID) and the sentinel — both
live estates run enforce; the code default log_only only shadow-records —
BLOCKs `I.manifest` on that agent's every action. The two PRs merged
back-to-back in one cloud session, this repo's first: field-platform#1
(bab3d91 → 1727de0, 09:27:30Z), Force-Field#1 (d841c25 → d14ffcc) 9 s
later. Shipped (bab3d91): `manifest.py` — `IrreversibleActions` model,
`Enforcement.irreversible_actions` + `.protected_paths` optional,
`SEAL_ALGORITHMS` / `Ledger.seal_algorithm` gain `sha-256-chain` (the
gate's LINEAR chain — tamper-evident, not tamper-proof); schema + all
four templates re-vendored from Force-Field `plugins/field/skills/field/`
into field-core `schema/` + `templates/`, schema + default template into
`plugins/field-agent/templates/` — all three schema copies are the same
git blob 8e03961 (content sha256 1f599e6d…; the CRLF checkout on
rog-command hashes 9b90d18f…), `SOURCES.md` stamp updated,
`verify_sync.sh` "templates in sync". Schema change ADDITIVE (`$comment`
revision 1.1.0; `schema_version` unchanged). Tests +4 in
`test_validation_parity.py`: schema property sets == Pydantic
`model_fields` per section (nothing else caught the new-key half of this
drift; the enum half was already pinned by
`test_vendored_schema_agrees_on_seal_algorithms`), templates carry the
`tool_call` budget (max 200/session) and validate, a manifest using every
gate key is VALID, an unknown enforcement key is INVALID. field-core
62/62 (project venv, Python 3.14.2, 2026-09-12); CI for #1 NOT checked
from rog-command (private repo, no `gh`). Re-vendor recipe for the next
drift: copy schema + 4 templates from Force-Field, mirror any new key in
`manifest.py` (the parity test fails until it matches), copy schema +
default template into field-agent, update the SOURCES.md stamp, bump the
plugin, run `verify_sync.sh`. Next lockstep trigger: Gate v1.2 plans
`kill_switch.local_sentinel` (Force-Field CHANGELOG Unreleased) — a new
key under `KillSwitch` (extra=forbid).
NOT done: (1) `plugins/field-agent/.claude-plugin/plugin.json` still
0.1.1 (unchanged ad7a79c→1727de0) although its vendored schema/template
changed — violates the 2026-08-29 LESSON below; installed plugins keep
the pre-gate files until a 0.1.2 bump + `plugin update`. (2) GB10 (image
636e4bb) and Fly (image e07cd5b) run pre-lockstep field-core in enforce:
a gate-key manifest registered there is INVALID → `I.manifest` BLOCK
until both are rebuilt at ≥1727de0 (dogfood manifests use no gate keys —
unaffected). (3) field-agent README/SKILL.md/command still call `field`
"design-time governance" — stale vs the runtime gate. (4) No crosswalk
control for `irreversible_actions`, `protected_paths` or the `tool_call`
rate limit. (5) `verify_sync.sh` still not in CI. Gate caveats carried
from the Force-Field CHANGELOG: regex matching is a tripwire, not a
sandbox; one kill_switch per manifest (an HTTP kill switch keeps its
meaning, the gate uses the default sentinel `.claude/state/KILL`); the
call counter is not locked against parallel tool calls; E4 measured
model-free only; `hooks.json` invokes `python3`.

**Windows check (2026-09-12, rog-command, model-free):** the gate runs
under Git Bash (`hooks/test/run.sh`: allow / DENY E3 / E2 / E1 / LEDGER
INTACT; launch ≈0.35 s; Store-alias `python3` 3.14.2 + PyYAML 6.0.3).
The PowerShell 5.1 fallback returns exit 1 but the deny JSON on stdout is
honoured (docs + 2.1.266 binary, not observed live); no `python3` →
non-blocking → nothing enforced (silent, as the CHANGELOG says). Live
`claude -p --plugin-dir` BLOCKED: local CLI logged out (`claude auth
login`). Report: `../tasks/windows-gate-verification-2026-09-12.md`
(FORCE-FIELD/tasks, the folder above both checkouts — NOT this repo's
tracked `tasks/`).

## Dogfood step 1 — Spin State's own agents on the GB10 (2026-09-08)
Decision (Don): the GB10 is the live DEMO + DOGFOOD estate for Spin State's
own agents and runs ENFORCE; the ADR 02 log-only pilot gate is deliberately
not being run there (gb10 override header says how to flip it back).
Found first: the GB10 compose stack had been fully `Exited (255)` for 6 days
after a host reboot (no restart policy) — the "burn-in" was not running.
Fixed: `restart: unless-stopped` on every service (base compose + proxy);
GB10 proxy CUTOVER APPLIED (single port :18080, Caddy path-routed, images
rebuilt on the GB10 at 636e4bb); all 9 /health OK through the proxy,
console 200, sentinel mode=enforce judge=off, ledger verify ok (285 events).
Reach path that works from Cowork on rog-command: `ssh.exe` exits 255 even
on `ssh -V` in that tool context, but **paramiko** with
`C:\Users\donal\.ssh\gx10_ed25519` as user `spinner` works (helpers at
`C:\Users\donal\.field-local\gb10_run.py`); the GB10 checkout pulls from the
local bare repo `~/git/field-platform.git`, fed by a `git bundle` SFTP'd
across (same commit hashes as rog-command/GitHub).
Shipped (636e4bb): `manifests/ssl-timekeeping-agent.yaml` +
`ssl-invoicing-agent.yaml` (REAL manifests, `field validate` VALID, copied to
the `field-data` volume at `/data/manifests/`), `agents/` (governed SKILL.md
sources with Enforced-vs-Declared + checklist self-review — NOT COMPLIANT on
C1 by construction: a Cowork skill cannot report token usage; stated),
`tools/provision_ssl_agents.py` (register → cap → 30-day token → scope and
never-granted probes) and `tools/field-rest.ps1` (heartbeat/check/spend over
REST for skills on rog-command, fail-closed enforce posture, actions-only
metering). Provisioned and VERIFIED live: both agents registered/active,
caps USD 5/daily, tokens expire 2026-10-08 (`~/.field-local/tokens-gb10.json`,
outside Drive); every scope action ALLOW, both escalation triggers
ESCALATE `E.escalation_trigger`, both never-granted actions BLOCK `D.scope`,
unknown agent heartbeat `killed=true`. Learned: an `E.escalation_trigger`
ESCALATE is a ledger verdict only — no governor escalation-queue item is
created — so the skills resolve it by explicit in-chat human approval,
recorded in the run report. Account skills (`invoicing-agent` updated,
`timekeeping-agent` new) proposed via Cowork from the `agents/` sources.

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
produced 53 items (see Next action + Open questions; full prioritized
list: https://claude.ai/code/artifact/35924f88-29d9-4d33-99b0-376ff72497c3).
CI on b8817c9 VERIFIED GREEN post-push (compose-smoke ran the proxy
end-to-end on x86_64: 10 health checks through :8080 prefixes + governed
smoke flow + ledger verify — the Caddyfile's first real run).

## Productionization step 2 — Fly sandbox estate packaging (2026-08-30)
The platform is now packaged as ONE container for a Fly.io Machine — the
public sandbox estate behind the Force-Field Portal (`integration/fly/`:
Dockerfile, Caddyfile, entrypoint.sh, fly.toml, README.md). The ten
served services bind 127.0.0.1 inside the container (the image installs
all eleven packages; compliance-crosswalk stays CLI-only, uncomposed by
design); the Caddy binary (copied
[SUPERSEDED 2026-09-12 by A0 — the images never installed
lifecycle-manager or attestation-reporter and now install thirteen
packages; compliance-crosswalk is composed and routed at /crosswalk, and
the estate serves thirteen services, not ten]
from caddy:2-alpine — static Go, runs on python:3.12-slim) is the only
0.0.0.0 listener (:8080) with the demo Caddyfile's exact route map on
loopback upstreams. entrypoint.sh mirrors the compose commands/ports,
exports loopback FIELD_*_URL (behavioral: forcegw only wires governor/
ledger clients when set), defaults FIELD_SENTINEL_MODE=enforce, and
supervises via bash `wait -n` — any child dying exits non-zero so Fly
restarts the machine. forcegw runs WITHOUT --mock (verified in cli.py/
api.py: keyless /health works; /v1/messages 502s honestly until
ANTHROPIC_API_KEY is set as a Fly secret; hygiene judge off by default).
Volume ff_data → /data; FIELD_SHARED_SECRET via `fly secrets set`, never
in fly.toml. New CI job fly-image-smoke builds the image from repo root
and runs the SAME health loop + governed smoke flow as compose-smoke
against the single container. Status: written and adversarially reviewed
(2026-08-30: every serve flag/port verified against each cli.py; forcegw
no-mock claim re-verified in api.py; fly.toml tomllib-parsed and ci.yml
yaml-parsed clean; entrypoint.sh confirmed LF, .gitattributes covers
*.sh; review FIXED a false "eleven services bind" count — ten serve,
crosswalk is CLI-only — and ADDED a TERM/INT trap to entrypoint.sh so
Fly stops don't hang to kill_timeout and SIGKILL the ledger). The
fly-image-smoke job has NOT yet run (this work is uncommitted at review
time — verify it green on first push; docker is unavailable locally).
**DEPLOYED LIVE 2026-08-30: https://force-field-sandbox.fly.dev** (app
force-field-sandbox, region yyz — `yul` no longer exists in Fly's region
list, fixed in fly.toml/README; machine 817eedf971947d, shared-cpu-1x
**1GB** — the 256MB default OOM-killed `console` at ~75 s and the
entrypoint supervisor correctly took the machine down; `[[vm]] memory =
"1gb"` now pinned in fly.toml; bump to 2GB if oom-kill reappears).
Deploy path: classic remote builder (`--depot=false` — the depot builder
timed out twice from this machine) + `--ha=false` (MANDATORY: single-
writer ledger must stay one machine; flyctl otherwise provisions two and
clones the volume). VERIFIED LIVE: all 9 /health OK through the proxy +
console 200 at root; sentinel mode=enforce judge=off; gateway mock:false;
x-field-auth gate proven (401 without secret, 201 with); ledger verify
ok at length 1. FIELD_SHARED_SECRET set via fly secrets (plaintext only
at ~/.fly/ff-estate-secret.txt on this machine — also needed as the
portal's ESTATE_SHARED_SECRET in Netlify env, set manually to keep it
out of session logs). fly-image-smoke CI job VERIFIED GREEN pre-deploy
on e07cd5b. Portal wiring: Netlify ESTATE_URL set; ESTATE_SHARED_SECRET
+ the GitHub repo link are the remaining human clicks. This is the
PRODUCT estate (sentinel enforce); GB10 remains the private burn-in
estate (log_only).

## Current phase
**v1.2 — 12-system closure (started 2026-09-12; plan approved by Don the
same day).** Plan: `tasks/todo.md` § "v1.2 — 12-system closure (2026-09)"
(P → A → B → C → D → F → E; one phase at a time; STOP after each phase
summary). Spec: `../tasks/claude-code-prompt-v1.2-12-system-closure.md`;
ground truth: `../tasks/audit-v2-12-systems-vs-production-build-2026-09-12.md`.
ESTATE CAVEAT: GB10 (image 636e4bb) and Fly (image e07cd5b) run pre-v1.2
code; every "served"/"scheduled"/"Enforced" claim in this section is
test/CI-proven until Don redeploys, and per-system estate status stays
Declared until then. Needs redeploy / decision by Don (grows per gate):
fly.toml memory 2 GB (A4); registry SQLite migration — forward-only, back
up /data/registry first (B4); `--mock` removal ⇒ GB10 keyless 502 on
/v1/messages until ANTHROPIC_API_KEY is set in the GB10 .env (D2);
FIELD_DOA_ROSTER / FIELD_LIFECYCLE_ROSTER files on /data + env (B1/A1);
FIELD_KILL_ENDPOINT_ALLOWLIST (B3); FIELD_LEDGER_RETENTION_DAYS ≥ 2555,
archive dir under /data, FIELD_LEDGER_ANCHOR_KEY custody (C2); crosswalk
daily egress (D4; DECIDED by Don 2026-09-13: FIELD_CROSSWALK_EVERY=86400 on
both estates, pinned by tools/tests/test_deploy_docs.py); ANTHROPIC_API_KEY
placement is Don's (GB10 .env, Fly secret; D2); FORCE_GATEWAY_URL estate-wide (D2e);
FORCE_GATEWAY_ENFORCE + ledger/attest signing keys (F); plugin 0.1.2 bump.
Added after the Phase A ops review (all land on the next `up -d` / deploy):
`FIELD_MANIFEST_DIR` now reaches the sentinel for the first time (compose/Fly
default `/data/manifests`) — manifest resolution CHANGES on two ENFORCE
estates; create `/data/manifests` or set `FIELD_MANIFEST_DIR=/platform` in the
estate `.env` to preserve today's behaviour. `FIELD_SHARED_SECRET` now reaches
containers: if the GB10 `.env` already carries it, the perimeter switches ON
and every host-side caller without `x-field-auth` starts getting 401 (an empty
value is inert in both directions). `FIELD_LIFECYCLE_EVERY=86400` arms a daily
sweep on both estates; with no roster each tick appends `lifecycle.tick_skipped`
to the hash-chained ledger indefinitely (skips no longer overwrite the last
sweep report — they go to `last_tick.json`). Three new containers on the GB10:
memory/CPU headroom there has never been assessed (only Fly was sized).
Added after Phase B (all land on the next `up -d` / deploy):
**the kill-switch is no longer stateless** — the first check-in or the first
`GET /liveness` creates `$FIELD_DATA_DIR/killswitch/heartbeats.sqlite3` on the
/data volume; local, unreplicated, in no backup routine, and a wiped /data
makes every agent read stale. **Existing routes change status code**:
`/kill/{id}`, `/revive/{id}` and `/drill/{id}` answer 409 for a `retired`
agent and `/kill/domain/{d}` skips retired agents into a new `skipped_retired`
list — any script that treated 200 as the only success path needs re-reading.
**New ledger events start appearing**: `kill.endpoint_skipped` on EVERY kill,
domain-kill and drill (the allowlist is unset, so the reason is always
`allowlist_unset` or `self_endpoint`), plus `kill.endpoint_called|failed` once
a host is allowlisted, `kill.drill.restore_failed`, `registry.attested` and
`lifecycle.decommissioned` — ledger volume per kill roughly doubles.
**`FIELD_MANIFEST_DIR` now has three readers, not one**: the sentinel on every
check, delegation-authority on every mint under a roster, and the kill-switch
on EVERY kill (it resolves and schema-validates the manifest before the
allowlist check). **Re-attestation is measured from a different field**:
`attested_at` else `created_at`, never `updated_at`. CORRECTED by the
2026-09-12 pre-flight walk: an earlier version of this sentence said the first
sweep after redeploy flags EVERY agent. That is false at the default 90-day
window — the oldest active `created_at` on the GB10 is 2026-08-08, so the first
agent falls due on 2026-11-06 (volatility-trader 2026-11-09, both ssl agents
2026-12-07; Fly's only agent 2026-11-29). No sweep runs at all without a
roster. Attest each agent before the first rostered sweep on or after
2026-11-06, or expect findings from then.
**Copy the manifests into /data/manifests BEFORE arming `FIELD_DOA_ROSTER`** —
under a roster an agent whose `manifest_ref` does not resolve cannot be minted
for (422 `D.scope`, by design) and `provision_ssl_agents.py` registers and
mints in one pass. **Payload shapes gain fields** (all additive, but a
strict-parsing consumer needs a look): `AgentRecord` gains
`attested_at`/`attested_by`; `delegation.mint` gains `doa_checked`/`doa_row`;
`KillReport` gains `endpoint_result`; `DrillReport` gains
`endpoint_confirmed_ms`; `Heartbeat` gains `last_seen`. **Four new routes
under existing proxy prefixes** (no Caddyfile change): `POST
/killswitch/heartbeat/{id}`, `GET /killswitch/liveness`, `POST
/delegation/oauth/introspect`, `POST /registry/agents/{id}/attest`.
**lifecycle-manager gained a RUNTIME dependency on spend-governor**; both
Dockerfiles install it in the right order, but the rog-command venv needs
lifecycle-manager installed too, because `tools/provision_ssl_agents.py` now
imports `lifecycle_manager.engine`. **The SDK fails closed on a pre-v1.2
estate**: `FieldAgent.checkin()` raises `HeartbeatUnreachable` on the POST's
405, and `integration/demo/agent/invoicing_agent.py` uses it as its only gate,
so the demo agent halts at step 1 until the kill-switch is redeployed. The two
PowerShell skills deliberately do NOT rely on the check-in to halt — they keep
`Get-FieldHeartbeat` as hook 3a for exactly this reason.
Premise corrections (2026-09-12, verified against 1727de0): (1) both
Docker images omit lifecycle-manager and attestation-reporter — the
"installs all eleven packages" line below is wrong; (2) `E.rate_limit`
already exists in field-core; only `D.grantor` is new; (3)
`FORCE_GATEWAY_URL` exists nowhere, `FIELD_GATEWAY_URL` is the CLI target;
(4) the only manifest resolver is the sentinel's — it moves to field-core
first (B0; DONE in 00bd644, three readers now); (5) the per-action throttle has no data source until D1 adds
`action` to spend rows; (6) every manifest the kill-switch could resolve
points back at its own /kill/{agent} — B3 needs a self-call guard (DONE in
f195168: header short-circuit plus a path skip, a test for each); (7)
`def test_` = 298 today (the "209 tests" figures below are stale); (8) the
verbatim v2 one-liners exist only as phrases quoted in the audit; (9) the
"probe /health from a separate call" rule lives in the parent-folder
lessons.md; (10) compose forwards NO host env into containers — every
operator-enabled variable needs a `${VAR:-}` passthrough line (A0).

**Phase A — DONE (2026-09-12), with one gate condition unmet (below).** The
three CLI-only systems are served: lifecycle-manager :8012 `/lifecycle`,
attestation-reporter :8013 `/attest`, compliance-crosswalk :8008 `/crosswalk`.
Commits ff1f836 (A0+A4 wiring), 6d7d4f3 (A1), 20528a0 (A2), f69f9ae (A3),
ab4cd84 (E1 source, delivered early).
- **A0/A4.** Both Docker images now install lifecycle-manager and
  attestation-reporter — they never did; STATE.md's "installs all eleven
  packages" (Productionization step 2) was wrong and is corrected here. compose
  gained the three URL anchors, the two missing ones (GATEWAY, FEDERATION) and
  `${VAR:-}` passthroughs, because compose forwards NO host env: without them
  Don cannot enable a roster/allowlist/key from an estate `.env`. Both
  Caddyfiles route the three prefixes ahead of the console catch-all;
  entrypoint starts thirteen services; fly.toml → 2 GB (needs redeploy); both
  CI health loops cover 12 prefixes + console and the fixed `sleep 20` is now a
  bounded per-prefix retry.
- **A1.** `POST /sweep` takes `roster_csv` or `FIELD_LIFECYCLE_ROSTER` and
  answers **503** with neither — an empty roster would orphan every agent.
  Auto-kill is reachable only through an explicit request-body flag (the
  kill-switch client is built inside the handler under that flag; the scheduler
  hard-codes it off; a grep-guard test proves no `AUTO_KILL` env lookup
  exists). `--every`/`FIELD_LIFECYCLE_EVERY` ticks after the interval, records
  `lifecycle.tick_skipped` when no roster is configured, and survives a raising
  tick. 20/20 (6 existing unmodified).
- **A2.** Served pack is an UNSIGNED, all-time draft; `since`/`until` answer
  422 naming C4 rather than silently returning all-time counts. 15/15.
- **A3.** `POST /pack` over the unchanged evidence-pack path: blank signer 422,
  stale flag 409 with the affected control ids, CLI still canonical; the
  FastAPI description no longer claims citations are stubs. 57/57.
- **Verified locally:** lifecycle 20, attest 15, crosswalk 57, field-core 62,
  field-agent 17, kill-switch 8, sentinel 59 — every pre-existing test
  unmodified. demo.sh wall times 16 s / 14 s / 3 s. `run_demo.sh` **exit 0 in
  33 s**, last lines: ledger INTACT, 1 active agent, conformance rate 71.4 %
  (unchanged), 1 BLOCK, 1 kill drill, 1 authority expiring within 30 days.
  compose/gb10/ci YAML and fly.toml parse; entrypoint.sh is LF; both Caddyfiles
  balanced with the console handle last. (`docker-compose.gb10.yml` fails
  PyYAML on its `!override` tag — pre-existing since the proxy cutover, not a
  regression.)
- **A-GATE CLOSED 2026-09-12 (e89d289).** The independent adversarial review
  was re-run on Don's instruction against ff1f836..ab4cd84 with two reviewers
  (code/honesty, wiring/ops). Both returned **fix-first, no blockers**; all six
  must-fixes and ten should-fixes are applied in e89d289. The two that mattered:
  (1) the `StrictBool` guard that makes "explicit literal `true`" real had NO
  test, so a one-token regression to plain `bool` would have let
  `{"auto_kill_orphans": "yes"}` arm the kill-switch with every test still
  green; (2) roster-less scheduler ticks were persisted OVER `last_sweep.json`,
  and since both estates ship with the scheduler armed and no roster, a daily
  tick would have erased the `swept_at` this README names as the only evidence
  a sweep ran. Both are now fixed and pinned by tests. Suites after the fixes:
  lifecycle 32 (was 20), attest 15, crosswalk 57, field-core 62, field-agent
  17; no pre-existing test modified. Original gate note follows for the record.
- **Gate condition that was unmet before the re-run — no independent review.** The Phase A
  build ran as five subagents; four (A0, A1, A2 and the adversarial reviewer)
  died mid-run on an account credit limit. A3 completed; A0's wiring and A2's
  code landed partially and were finished, verified and corrected in the main
  session, and A1's tests, serve verb and docs were written there too. The
  plan's "adversarial review agent signed off" is therefore UNSATISFIED for
  Phase A: the checks above are self-verification, not an independent read.
  Re-run the reviewer against ff1f836..ab4cd84 before Phase B, or accept the
  gap explicitly.
- **Still CI-only:** docker is not installed on this machine, so the images and
  both smoke jobs are proven by CI on the pushed commit, not locally.

**Phase B — DONE (2026-09-12).** The authority chain. Commits 00bd644 (B0),
9e5b642 (B1+B2), f195168 (B3 + B4's kill-switch half), 017a10f (B4).
- **B0.** `ManifestResolver` lifted out of the sentinel into
  `field_core.clients`, plus `resolve_manifest` / `resolve_manifest_detail`
  over one resolver per manifest dir so the mtime cache survives. The sentinel
  still calls the CLASS, so its instance spy test is untouched. B1, B3, C2 and
  C3 all needed "resolve a record's manifest_ref"; there was exactly one
  resolver and it lived inside the sentinel.
- **B1.** `FIELD_DOA_ROSTER` (YAML) gates every mint before any ledger write:
  unreadable roster 503, grantor absent or inactive 403 `D.grantor`, scope
  beyond the grantor 403, manifest unresolvable or scope beyond it 422
  `D.scope`, TTL beyond `max_ttl_days` 403. `max_spend_usd` is recorded, NOT
  enforced, and the README says so. Roster unset is byte-for-byte the old
  behaviour with `doa_checked=false`; the eight existing tests are unmodified.
- **B2.** `POST /oauth/introspect` parsed with `parse_qs` off the raw body
  (python-multipart is not installed; a `Form()` dependency would break
  `create_app()` for seven suites). FIELD scopes contain spaces, so `scope` is
  the RFC 7662 string and `scope_list` carries the exact strings. Anything not
  active answers exactly `{"active": false}`.
- **B3.** A kill now resolves the agent's manifest and calls its own halt
  endpoint — fail closed throughout: allowlist unset ⇒ no call ever; exact
  `urlsplit(...).hostname` matching (userinfo and suffix tricks each have a
  test that fails if the comparison is weakened); `follow_redirects=False`
  pinned on the outbound client, because an allowlisted host answering `302
  Location: http://169.254.169.254/` would otherwise walk the signal off the
  allowlist; header + path guards against recursing into itself; host-only
  results so endpoint credentials never reach a report or the ledger. Liveness:
  `POST /heartbeat/{id}` records `last_seen` in SQLite (lazily — a kill-switch
  nobody checks in to creates no file), `GET /liveness` lists stale vs live.
  Stale means NO CHECK-IN IN THE WINDOW, never evidence a process is dead.
- **B4.** `attested_at` / `attested_by` on the registry record only (Create and
  Update forbid extras, so a PATCH cannot forge a re-attestation); `POST
  /agents/{id}/attest` is the sole writer; forward-only SQLite migration.
  Re-attestation now runs from `attested_at` else `created_at` and NEVER the
  edit timestamp — the real defect was that any PATCH moved `updated_at`, so a
  kill/revive cycle reset staleness to zero and hid the agent. `lifecycle
  provision` (validate → register → cap → mint; INVALID manifest exits 1 with
  zero side effects; the cap comes from the governor's own arithmetic) and
  `lifecycle decommission` (revoke → kill only if active → retire → ledger;
  act-first through a ledger outage). All four status-writing kill-switch
  routes now refuse a retired agent.
- **Verified locally:** 501 tests green across 13 services and 2 packages
  (kill-switch 55, delegation 39, registry 17, lifecycle 56, sentinel 59,
  crosswalk 57, gateway 33, attest 15, console 10, replay 5, field-core 92,
  field-agent 21, and the shared job-1 run at 245). `verify_sync.sh` exit 0,
  six templates in sync. All 13 service demos exit 0 (ops-console serves until
  interrupted — reaching its banner is its success state); wall times
  delegation 17 s, kill-switch 15 s, lifecycle 14 s, registry 3 s,
  spend-governor 12 s, sentinel 24 s, attest 13 s, federation 11 s, replay 9 s,
  ledger 7 s, gateway 6 s, crosswalk 3 s. **`run_demo.sh` exit 0 in 32 s** with
  `FIELD_DOA_ROSTER` unset: ledger chain INTACT over 25 events, 1 active agent,
  conformance rate 71.4 %, 1 BLOCK, 1 kill drill, 1 authority expiring within
  30 days. (One diagnostic for the record: the spend-governor demo failed on
  its first run against an orphaned service stack the ops-console demo had left
  listening on 8001-8006; it passes on a clean machine. Not a regression.)
- **Still CI-only:** docker is not installed here, so both image builds and the
  compose smoke job are proven by CI on the pushed commit, not locally.
  CORRECTED 2026-09-12: an earlier version of this bullet said "the only git
  remote is `gb10` over SSH". That was wrong — a `git remote -v | head -2` had
  truncated the list. The repo has TWO remotes: `origin`
  (https://github.com/SpinStateLabs/field-platform, where CI runs; Phase A
  reached it at 415e3c8) and `gb10` (the bare repo the GB10 checkout pulls
  from). Phase B was pushed to both at the X0 deploy.
- **B-GATE CLOSED 2026-09-12 (f732a09).** Two independent adversarial reviewers
  (security; docs/ops) ran against 415e3c8..017a10f. Both returned blockers —
  eight in total — and all are fixed in f732a09, each guard mutation-checked
  (neuter it, the suite must fail; restore it byte-for-byte). The four that
  mattered:
  (1) **A regression this phase introduced.** Both ssl skills had hook 3 moved
  from `Get-FieldHeartbeat` (GET) to `Send-FieldCheckin` (POST). On a pre-v1.2
  kill-switch — which is what both estates run — that POST is a 404/405 that
  the shim deliberately does not treat as a liveness verdict, so the change
  removed the only pre-work halt gate the two REAL agents had. Both calls now
  run, and the shim comment says why.
  (2) **A halt signal could re-enter the kill-switch.** The recursion guard
  matched only `/kill/{the-agent-being-killed}`, so a manifest pointing at
  `/heartbeat/{another-agent}` was called — forging a check-in that
  `GET /liveness` reported as live. The guard now matches route SHAPES.
  (3) **`registry attest` bypassed the ledger**, while SPEC and README both
  said otherwise — and `attested_at` is the only field that clears a
  `lifecycle.reattestation_due` escalation, so that was a compliance flag
  cleared with no audit record.
  (4) **Two "Enforced in code" rows cited evidence that did not prove them:**
  the suffix weakening of the SSRF allowlist was unpinned (`host.endswith(...)`
  passed all 55 tests while signalling `notallowed.host`), and the cents test
  used 0.07, where `int()` and `round()` agree, so it passed against the
  truncation it was named to catch.
  Also fixed: the kill-switch SPEC asserted the opposite of the code shipped
  beside it; `lifecycle provision` was a fifth registry writer with no
  `retired` guard; four correct-but-untested guards; and a false claim served
  in the crosswalk's live OpenAPI schema. Suites after the fixes: **524 green**
  (266 + 258), no pre-existing test modified; `verify_sync.sh` exit 0; demos
  re-run after the code changes (registry 2 s, delegation 16 s, kill-switch
  14 s, lifecycle 14 s) and `run_demo.sh` exit 0 in 31 s, chain intact.

**v1.2 REVISION 2.1 — production on both estates (Don, 2026-09-12).** Don
lifted the original "do not deploy" boundary: "make sure that all components
are deployed ... I want all features working like we are going to production
... deployed to the public side and the private GB10 ... fix the missing
registry", plus "decommission smoke-agent after the redeploy", "go ahead and
attest all the agents" and "go ahead and deploy when the runbook is ready". The
revised plan (attacked by five adversarial lenses and judged before adoption)
makes deployed-and-verified-live on BOTH estates the definition of done at every
gate, adds a dedicated canary agent per estate so no live check ever mutates a
real agent, and orders the arming of every fail-closed switch with a canary
check between each.

**X0 — GB10 DEPLOYED 2026-09-12 21:25–21:28 UTC (commit 411ffbc, Phases A + B).**
- **Pre-flight.** Eight read-only probes of both estates, a runbook, and four
  adversarial reviews of that runbook (data loss, blast radius, ordering, false
  green). No blocker on the forward path; every fix-first is built into
  `docs/runbooks/v1.2-deploy-rollback.md`.
- **Build proven before the outage.** v1.2 images built on the GB10 beside the
  live stack, then run in throwaway containers: the new registry image serves
  `/agents/{agent_id}/attest`, the old one does not.
- **Rollback assets.** 11 images tagged `:pre-v1.2` BY RUNNING IMAGE ID (never
  from `:latest`), saved to `~/field-backups/images-pre-v1.2.tar.gz` (82 MB,
  sha256 recorded) so a prune elsewhere on the shared host cannot delete them;
  git marker `pre-v1.2-gb10` at ad7a79c; built image IDs recorded to
  `image-ids-built-v1.2.txt`.
- **Outage ~35 s.** Quiesced backup written as `.partial`, then verified
  before promotion: 289 lines, chain verifies from GENESIS to the pinned head
  `1403fba4b898…`, `PRAGMA integrity_check` ok on all four SQLite files,
  registry still the 8-column schema. Promoted, `RESTORE_SOURCE` written, copied
  off-host to rog-command with matching sha256. Then `up -d --no-build
  --force-recreate` (required: the proxy's config hash does not change, so it
  would otherwise keep the old Caddyfile inode). The one-way registry
  migration ran at this point.
- **Verification (evidence that can fail).** 13 service containers on the
  exact recorded build IDs; `estate_probe health` 25/25 (every prefix names
  the right service AND one data route per service serves); `continuity` 3/3
  (history to 289 unchanged, /health /events /verify consistent); the
  registry's served OpenAPI lists `POST /agents/{agent_id}/attest` — **the
  missing registry route is fixed on the private estate**; all four agents
  migrated with the new keys; sentinel still `enforce`; 14 containers, 0
  restarts, stable across a 60 s re-read; 0 tracebacks in the logs.
- **Canary and catalogue.** `canary-gb10` provisioned with the real
  `lifecycle provision` inside the estate (validate / register / cap / mint);
  `canary-gb10-retired` registered and decommissioned as refused-kill's only
  legal target. C0 5/5, Phase A + B live catalogue 21/21 (introspection,
  check-in with the exact `last_seen`, audited kill → BLOCK `E.kill_switch` →
  audited revive → ALLOW, drill restoring to `active`, attestation), retired
  guard 4/4, canary token revoked at the end.
- **Don's writes, recorded as executed by a Claude session on his 2026-09-12
  instruction.** `ssl-invoicing-agent` and `ssl-timekeeping-agent` attested by
  "Don Hagell" (21:27:57Z). `smoke-agent` decommissioned by "Don Hagell":
  token revoked, killed, retired, `lifecycle.decommissioned` ledgered. The
  collateral check passed 9/9 — every event about a non-canary agent since
  the step began is one Don asked for.
- **NOT attested: `volatility-trader`.** Verified independently: it runs from
  cron every 4 h in shadow mode and 156 of its 190 runs have HALTED, every one
  since 2026-08-18, because its FIELD URLs default to local ports the stack
  stopped serving at the proxy cutover. Governance is failing closed (an
  unreachable heartbeat halts it), not failing open. Its token expires
  2026-09-19T22:28Z. Attesting it would have recorded a false "reviewed and
  fine", so it waits on Don (D2: repair its config, attest with a finding, or
  decommission).
- **New pin:** GB10 ledger 321 events, head `d9f71e7c4e231f92…`.
- **Soak PASSED:** 21:28:36Z–22:28:41Z, five rounds 15 min apart, every round
  health 25/25, continuity 3/3, canary 5/5, restart counts unchanged, 0
  failures; soak token revoked.

**X0 — FLY DEPLOYED 2026-09-12 22:30:08–22:30:34 UTC (release v2).** X0 is
COMPLETE on both estates.
- Pre-deploy: public ledger pinned in-machine (1 event, head
  `f262a73886800a63`); the old image's health check FAILED on exactly the three
  routes A+B add (a live negative control that the probe discriminates on
  production); rollback references recorded — release **v1**
  `registry.fly.io/force-field-sandbox:deployment-01M1AM62F6J7WST7NS3V5YNZCD`,
  on-demand volume snapshot **`vs_a9pJwx7XnN9xsmZl24P6n0mN`** (created, 5-day
  retention), machine config saved.
- Deploy: `fly deploy -c integration/fly/fly.toml --image
  registry.fly.io/force-field-sandbox:v1-2-ab-97f93d1 --ha=false` — the exact
  image the smoke machine proved. Fly waited on the new health checks before
  calling the machine good.
- Verified: exactly one machine `817eedf971947d`, still on
  `vol_rkgkl26n65jpyk64`, running `v1-2-ab-97f93d1`, `shared-cpu-1x:2048MB`,
  checks 3/3. In-machine with the perimeter on: health 37/37 (every data route
  serving authenticated and 401 unauthenticated), continuity 3/3, `canary-fly`
  provisioned on the PRODUCTION volume, C0 5/5, catalogue 21/21, retired guard
  4/4, collateral 0 events about any non-canary agent, token revoked. Ledger
  now 25 events, head `0ea48b358499262f`. Memory at 2 GB: 842 MiB RSS, 1221 MiB
  available. Externally every one of the twelve prefixes answers `/health` by
  its own service name over the public URL, and data routes answer 401.
- Fly's only pre-existing agent is `smoke-live` (a 2026-08-31 deploy smoke
  record, no manifest). Not touched: Don's decommission instruction named the
  GB10's `smoke-agent` only. Reported to Don.
- **CI VERIFIED 2026-09-12** (read through Don's signed-in browser; the repo is
  private, so the API and an unsigned browser both answer 404). `ci #39`
  (97f93d1, all of Phase B), `#40` (411ffbc, X0 prep) and `#41` (06b4aa6): every
  job green — the tests matrix on Python 3.11 / 3.12 / 3.13 / 3.14,
  `compose-smoke` (x86 image build plus the governed flow through the proxy) and
  `fly-image-smoke`. The new step "Test estate_probe" reports **27 passed**
  (8.5 s on Linux). `#32`–`#37` green. The one red run, `#38` (415e3c8, a
  docs-only commit), failed only `compose-smoke`, in 21 s, while pulling
  `python:3.12-slim`: Docker Hub's token endpoint reset the connection
  (`failed to fetch oauth token ... connection reset by peer`). No health check
  or governed-flow step ran, and the identical code passed in `#37` before it and
  `#39` after — infrastructure, not code.
- **`smoke-live` DECOMMISSIONED on Fly 2026-09-12** on Don's instruction:
  revoke / kill / retire / ledger all ok, `lifecycle.decommissioned` by "Don
  Hagell", collateral 6/6 (every new event about `smoke-live`), continuity to the
  25-event pin holds. Public ledger now 30 events, head `3726bfdc9d54048d`.
- **Fly image proven on Fly before the public machine is touched.** Because CI
  on a private repo is unobservable from here, the exact pushed image
  (`registry.fly.io/force-field-sandbox:v1-2-ab-97f93d1`, sha256 `9488c2ff…`)
  was run as a service-less, volume-less smoke machine in the app (no public
  routing; production volume untouched), then destroyed. Inside it, with the
  real perimeter on: health 37/37 (every data route serving authenticated AND
  401 unauthenticated), canary 5/5, catalogue 21/21, retired guard 4/4, revoke
  2/2. **Memory at 1 GB: 836 MiB RSS at idle, 227 MiB available of 962 MiB,
  no swap** — measured, not estimated, and the reason the deploy uses the 2 GB
  in fly.toml (about $5/month more).
- **Script bugs found and fixed during the run, none of which changed
  estate state:** phase 2's final health wait used `--retry-connrefused`,
  which does not retry a connection RESET during cold start (the estate was
  healthy on the next read); phase 4 parsed `pin`'s whole output instead of
  its last line and stopped before its first write (confirmed: ledger still
  289, canary absent).

**volatility-trader REPAIRED and ATTESTED on the GB10 (Don's D2 answer "yes
repair it", 2026-09-12).**
- `~/vt/secrets.env` now points every FIELD URL at the proxy (:18080) and
  carries a freshly minted token `b05d1424…` (expires 2026-10-12); the
  pre-repair file is backed up in `~/vt-repair/20260912T232344Z/`. The edit
  and the check are two scripts with recorded sha256 (`setenv.py` 9375b9eb…,
  `verify_vt_field.py` 8f75f1bb…), run under vt's own `~/vt/.lock`.
- **First scheduled run after the repair passed:** cron run
  `run-20260913-0005` exit 0 (`run ok`, shadow mode, 0 entries / 0 exits, 642 s),
  0 failure markers, no cron skips; ledger shows `conformance.allow` ×2,
  `spend.recorded` (1 c), `trading.run_completed`; governor `OK`. The 156
  HALTs since 2026-08-18 were the fail-closed symptom of the stale URLs.
- Attested by "Don Hagell" at 2026-09-13T00:16:20Z, AFTER that run proved it
  healthy. GB10 ledger 346 events, head `4f1b0777…`.
- **Left alone, reported:** an older vt token `035e4087…` whose minter is not
  identifiable from the ledger (expires 2026-09-19). Not revoked without Don.
- **Token renewal (Don: "renew the token automatically before it expires",
  "install renewal for the ssl agents too"):** `tools/renew_token.py` is being
  built and adversarially reviewed (uncommitted); not installed yet. Until it
  is: vt's token expires 2026-10-12, both ssl tokens 2026-10-08.

**X1 + C0/C1 COMMITTED 2026-09-13 (93d80a7, db5ad33), pushed to origin and
gb10; CI `#42` success.** Code only — nothing armed, nothing redeployed:
file-sourced perimeter secret in `tools/field-rest.ps1` (and a 200 reply that
is not a verdict now fails closed), `tools/generate_doa_roster.py` (+ J9
`--tokens`), lifecycle roster aliases, `delegation doa check`, ledger time
filters and offline-verifiable export bundles. Every re-verifier PARTIAL was
closed before commit with a test and a killed mutant (tail-by-one and filtered
genesis in the bundle, implicit-output and env Trace-2 leaks in the shim, TAB /
NBSP / U+3000 after an unquoted roster comma, naive `--tokens` timestamps). The
GitHub API answers `private: false` for the repo as of this read.

**Phase C BUILT + store/renewal hardening, 2026-09-13 — committed, NOT deployed.**
- **C2 (ledger rotation by rename + append-only journal, spec design A + G1–G7),
  C3 (replay RACI from data), C4 (attestation window + Ed25519 signature,
  canary row excluded), infra (`build_sha` on every `/health`, `field-manifests`
  / `field-keys` volumes, CI `compose-upgrade-smoke`).** The review had 6
  lenses. Every re-verifier residual is CLOSED or narrowed to exact wording.
  - The last closes: every archived journal entry now needs its own evidence;
    `/verify` answers `ok=false` on an unparseable record, never a 500; the
    probe's gate row is bracketed against interleaved canary appends; the
    runbook's rotation anchors are written under `/data` and then copied off-host.
  - Local suites green: sealed-ledger 315 (+3 skipped), attest 56, replay 74,
    lifecycle 95, combined core 657, estate_probe 43.
  - NOT run anywhere yet: Linux / GB10 latency at 100k, Python 3.11, docker, the
    `compose-upgrade-smoke` job, anything on either estate.
  - Documented limits: a ledger restarted on an open segment holding an
    unparseable line does not start (fails closed); a journal line plus a posted
    `ledger.retention.applied` event naming the right sha256 hides a deleted
    segment.
- **SQLite:** the 5 stores (delegation, registry, kill-switch, governor,
  federation) shared one connection with unlocked reads; each had hundreds to
  thousands of wrong or failed answers under 8-thread stress. Every connection
  use is now locked, pinned by stress tests and an AST lock-coverage test.
  - A concurrent PATCH could silently revert a kill (168/200 trials): update is
    now atomic.
  - spend-governor no longer opens duplicate escalations, and the **first
    resolver wins** (a different second resolver gets 409).
  - The kill-switch heartbeat store build is locked; token introspection runs
    off the event loop; a PATCH with an empty name/owner returns 422.
- **Token renewal:** `tools/renew_token.py` 1.5, `tools/ssl-verify-token.ps1`,
  and runbook `docs/runbooks/token-renewal.md` with sha256 pins.
  - All original blockers closed and re-verified.
  - It does NOT renew a revoked token without `--renew-revoked` (a revocation
    is the kill), and it requires a verify command that uses `{new_token}`.
  - `field-rest.ps1` no longer falls back to the real token file when
    `FIELD_TOKENS_FILE` names a missing file.
  - Not installed yet.
- **Incidents (disclosed):**
  1. A verifier mutant sent the real `ssl-invoicing-agent` token to a local
     127.0.0.1 test harness. It never left the machine. Remedy: its first
     forced renewal revokes it.
  2. The Sonnet test sweep killed three pytest processes that belonged to a
     concurrent mutation run of this session's own work; no files were changed.
- **Token renewal INSTALLED 2026-09-13 13:31–13:34Z** (executed by a Claude
  session on Don's instructions "renew the token automatically before it
  expires" and "install renewal for the ssl agents too"). CI `8a8360b` was
  green on every job first (tests 3.11–3.14, compose-smoke,
  compose-upgrade-smoke first run, fly-image-smoke).
  - **GB10 vt:** `~/vt-renewal/` holds renew_token.py 1.5, verify_vt_field.py
    and verify-vt.sh; `sha256sum -c SHA256SUMS` passes. The crontab line
    `35 14 * * * … # vt-token-renewal` runs daily at 14:35 local; the vt-runner
    line is unchanged. Both dry runs rc 0. **Forced renewal proven:**
    `b05d1424 → fe2b386b` (expires 2026-10-13T13:32Z). vt's own client verify
    passed (API key absent, enforce ALLOW, D.scope BLOCK, governor OK); old
    token revoked; `token.renewed` ledgered 13:32:36Z; journal cleared;
    secrets.env still mode 600.
  - **rog-command ssl:** `C:\Users\donal\.field-local\renewal\` holds
    renew_token.py (pin 3a068358…) and logs. Task Scheduler
    `\FIELD\token-renewal-ssl-timekeeping-agent` (daily 14:50) and
    `\FIELD\token-renewal-ssl-invoicing-agent` (daily 15:05) are both
    Interactive logon, no stored password, StartWhenAvailable. Check and cmd.exe
    dry runs rc 0. **Forced renewal of ssl-invoicing-agent proven:**
    `870806ca → 91a44419` (expires 2026-10-13T13:33Z). The shim verifier passed
    4/4. The locally exposed token `870806ca` is REVOKED (incident 1 closed).
    ssl-timekeeping-agent `561acf06` is not forced; it renews from ~2026-09-28.
  - Unchanged: vt token `035e4087…` (minter unidentified, expires 2026-09-19),
    left for Don. When A2 arms, both installs need `--secret-file` (runbook
    §3.9, §5.6) BEFORE the perimeter goes on.
- **Phase C DEPLOYED on both estates, 2026-09-13 (commit 08df159, CI `8a8360b` green on every job).**
  - **GB10:**
    - Built beside the live stack; every image's `build_sha` is 08df159.
    - Rollback assets: `:pre-phase-c` tags by running image ID,
      `~/field-backups/images-pre-phase-c.tar.gz` (82 MB, sha256 recorded), git
      tag `pre-phase-c-gb10`.
    - Outage 13:37:04–13:37:09Z. The quiesced backup verified before promotion
      (368 events to head `c672d207…`, 5 SQLite integrity ok) and was copied
      off-host with a matching sha256. `manifests-admin` seeded 4 manifests
      into `field-manifests`.
    - Verified: 14 containers on the recorded build IDs, health 39/39 with
      `--expect-build-sha`, continuity 3/3, restarts 0 and stable over 60 s,
      0 error lines.
  - **Fly:**
    - Image `v1-2-c-08df159` (75 MB) was proven on a service-less smoke machine
      first: health 51/51 with the perimeter on and the build sha, 845 MiB RSS,
      1.2 GB available. The machine was destroyed afterwards.
    - Snapshot `vs_yG6K149mDMG4u1nNPNNp2VNO`; rollback is release v2
      (`v1-2-ab-97f93d1`).
    - Deploy is release v3: one machine on `vol_rkgkl26n65jpyk64`, 2 GB,
      checks 3/3. In-machine health 51/51, continuity 3/3 to 30 events.
      Public `/health` 200, data routes 401.
  - **C-gate results:**
    - (1) pins: GB10 368 / `c672d207`; Fly 30 / `3726bfdc`.
    - (4) Export on each estate:
      - The served bundle was copied out and verified off-box with `ledger
        verify-export`: exit 0, `filters: none — every index 0..N is exported
        (verified)`, printed head_hash == pin.
      - A one-line edit fails, naming its index (GB10 100, Fly 10).
      - A tail deletion with the head rewritten fails too (GB10).
    - (5) Served sub-window packs are unsigned, and every window count equals
      a recount from `/ledger/events`:
      - GB10, 2026-08-18..19: 12 counts, 5 differ from all-time.
      - Fly, 2026-09-13: 12 counts, 1 differs. The 2026-09-12 window equalled
        all-time because every counted Fly event is inside it.
    - (6) GB10 vt 2026-08-18 replay: first failure `D.expired`. R = registry
      owner, A = expired grant covering the action, C = manifest
      kill_switch.authorized_operators, I = "Don Hagell — Spin State Labs
      (manifest identity)"; manifest_resolved true.
    - (7) `/retention/check` answers 2555 days with 0 unresolvable and
      0 offending on both estates.
    - Canary suite on both estates: canary 5/5, catalogue 23/23, refused-kill
      4/4, collateral 3/3, revoke 2/2.
    - **(2) A4 anchor key + (3) the ONE rotation per estate — DONE 2026-09-13
      on Don's decision** (custody: key on-box, public key off-box; "rotate
      both now"; operator "Don Hagell", reason "v1.2 C-gate rotation").
      Executed by a Claude session. One-way from here: rollback below Phase C
      is fix-forward only (runbook §3).
      - **GB10:**
        - Key `field-keys:/keys/ledger-anchor.pem` (0600), fingerprint
          `3f2da2021812ea481a7c3d2cf013430787007dc97b5fb773eabb16765bccf27f`.
        - `FIELD_LEDGER_ANCHOR_KEY` is set in `integration/demo/.env` (compose
          ignores `~/field-platform/.env`; the first attempt stopped safely on
          that).
        - Rotation 14:12:26Z: segment 1 = indices 0..454, head `d751be85…`.
        - `/verify` ok, length 592, segments 2. The open segment's first
          event (`ledger.segment.rotated`) links to the closed head. The
          signed anchor verifies with the public PEM.
        - Canary `/check` during the rotate: p95 26 ms, max 33 ms, 202/202
          OK. Continuity 3/3; health 39/39.
      - **Fly:**
        - Key `/data/keys/ledger-anchor.pem` (0600), fingerprint
          `f25425f3b098fab84b7ae35a833806fb63960d8f13eb4ee27ec23b2d1e7c10de`.
        - Path in `fly.toml` `[env]`, release v4 (same image).
        - Rotation 14:15:26Z: segment 1 = indices 0..115, head `1d33cc33…`.
        - `/verify` ok, length 241, segments 2, link ok, anchor verifies.
        - Canary p95 40 ms, 190/190 OK. Continuity 3/3; health 51/51.
      - Both public PEMs, fingerprints, rotation anchors and records are in
        `C:\Users\donal\.field-local\backups\anchors\`. Fingerprints were
        re-derived off-box and match.
      - The canary load wrote about 200 labelled gate-verification events per
        estate.
    - **C-gate: all seven adds PASS on both estates.**
- **X1 ARMING COMPLETE on both estates, 2026-09-13** (Don: "continue with X1
  arming"; A3 held for vt's 16:05Z run on Don's call). Executed by a Claude
  session. Every step ran C0 after arming; any failure would have disarmed
  automatically. None did.
  - **A1 `FIELD_LIFECYCLE_ROSTER=/data/owners.csv`.** The roster is `Don Hagell`
    (alias `Don Hagell, Spin State Labs`) plus `FIELD canary`. **D3 is still
    provisional:** Don has not yet confirmed the two strings are one human.
    - GB10, 14:21Z: sweep 1 (humans only) found exactly one orphan,
      `canary-gb10`, with 0 `kill.*` events; with `FIELD canary` added, sweep 2
      found 0 orphans. Health 39/39, continuity 3/3, canary 5/5, collateral 5/5.
      The soak ran **59 min** (1 min short of the hour) and was clean: health,
      0 restarts, findings.
    - Fly, 15:23Z (release v5): the same sweeps (one orphan `canary-fly`, then
      0), canary 5/5, collateral 3/3.
  - **A2 `FIELD_SHARED_SECRET` (GB10), 15:20:51Z.**
    - The secret was generated on the GB10 into `~/.field-local/estate-secret`
      (0600, 64 bytes). It was copied file-to-file to
      `C:\Users\donal\.field-local\gb10-estate-secret`; sha256 `0fc410be…` on
      both ends. The value was never printed.
    - Every caller held it before arming:
      - vt's `secrets.env` line 7 (pinned `setenv.py`, file-to-file); vt's
        own-client verify passed 16/16 with the header;
      - the vt renewal cron line and both ssl renewal tasks (`--secret-file`),
        each dry-run rc 0;
      - the ssl shim, `auth=file`.
    - After arming:
      - All 13 service containers hold the secret (digests match).
      - Health 51/51 with the perimeter; unauthenticated `/registry/agents` 401,
        authenticated 200; console `/` 200.
      - Canary 5/5 (services authenticate to each other).
      - ssl heartbeats `killed=false` with the header, HALT (401) without it.
      - J21 hook probe as `canary-gb10`: heartbeat, check-in, check ALLOW, spend
        OK. N1: `/liveness` lists `canary-gb10` live.
      - vt proof 16/16 under the perimeter.
    - **vt's 16:05Z cron run under the perimeter: `run ok`, exit 0, 0 markers.**
      Soak 61 min clean.
    - D4: Don unlocked the console. Its log shows `/api/overview` 200 from his
      tab.
    - Fly: already armed; its A2 canary checks pass.
  - **A3 `FIELD_DOA_ROSTER=/data/doa-roster.yaml`.** Generated in-estate by
    `tools/generate_doa_roster.py --tokens` from live registry and token data.
    - GB10, 16:22:43Z:
      - Rows: `Don Hagell` (4 scopes), `Don Hagell, Spin State Labs` (19),
        `FIELD canary (gate verification)` (5).
      - Pre-arm dry run passed for all 4 live real grants against the placed
        file.
      - Off-roster mint 403 `D.grantor`; rostered canary mint 201, revoke 200.
      - All 4 live real tokens introspect `active=true`.
      - Canary 5/5 (canary tokens are now minted as grantor `FIELD canary (gate
        verification)`); ssl heartbeats ok.
      - Soak 61 min: health 51/51, continuity, 0 restarts, 0 error lines.
    - Fly, 17:25Z (release v6): 2 rows; dry run ok; 403 / 201 / 200; canary
      5/5; collateral 3/3; N1 `canary-fly` live after a check-in.
  - **Still to record:** the lifecycle scheduler's first scheduled `swept_at`
    (the plan's 25-hour soak). Every recreate restarts its 24 h interval, so
    expect ~2026-09-14 16:23Z on the GB10 and ~17:24Z on Fly.
  - **Disarm lines:**
    - GB10: restore `~/field-backups/env-before-a{1,2,3}` over
      `integration/demo/.env`, then `up -d --force-recreate --no-build`.
    - Fly: `fly secrets unset FIELD_DOA_ROSTER` / `FIELD_LIFECYCLE_ROSTER`.
  - **Don's remaining X1 items:** D3 confirmation; D15 vt manifest
    `sha-256-merkle` → `sha-256-chain` (his file). The first real ssl skill
    run under the perimeter is Don's.
- **X4 cross-estate witness BUILT, DEPLOYED and A5 ARMED, 2026-09-13** (Don:
  "continue with X4").
  - **Code:** commit `0e4f976`, CI green on every job.
    - Build → one review (3 fix-first, 3 nits) → fixes → independent verify:
      5 CLOSED, 1 PARTIAL. The partial (compose-profile behaviour) is now
      proven live.
    - Suites: sealed-ledger 368, lifecycle 117, field-core 128, tools docs 94.
  - **GB10 deploy** 21:33Z: `pre-x4` rollback images saved, quiesced backups
    of field-data and field-manifests verified before promotion (632 events,
    2 segments), outage about 3 s. Health 51/51 (perimeter + build sha),
    continuity 3/3, 0 restarts, 0 error lines.
  - **A5 on the GB10**, 21:35:06Z: `COMPOSE_PROFILES=witness` +
    `FIELD_WITNESS_EVERY=3600` in `integration/demo/.env` (previous copy:
    `~/field-backups/env-before-a5`); only `witness` + `lifecycle` were brought
    up.
    - Witness host `584bdbde225d`; mounts are field-keys `/data/keys` ro plus
      the Dockerfile's anonymous empty `/data` volume, not field-data.
    - Logs: direction 1 appended; "direction 2 not live (D5)" every tick.
  - **Fly deploy:** image `v1-2-x4-0e4f976` smoked first (51/51, 844 MiB);
    snapshot taken; release v7. Health 51/51, continuity 3/3 to 255, all
    arming envs intact.
  - **Done-when evidence:**
    - The GB10 ledger holds 2 `anchor.remote{estate: fly}`, both authored by the
      witness container (`observer.host` = its hostname, `started_at` = its
      start) and signed. The second was written at 22:35:06Z, later than start
      plus 3600 s.
    - On Fly, `ledger verify-witness --estate fly --events-file <GB10 export>
      --pubkey <GB10 anchor pub> --path /data/ledger/events.jsonl` exits 0:
      2/2 hold against Fly's chain (length 255), 2 signatures verified.
    - Negative control: one head_hash hex flipped ⇒ exit 1 "WITNESS FAILED —
      anchor 1 … signature invalid".
    - The export and edited copy are in
      `C:\Users\donal\.field-local\backups\anchors\`.
  - **Not live (stated):** direction 2 (GB10 → Fly) until D5. Fly never
    initiates without D6. GB10 down ⇒ both directions stop. The lifecycle
    witness finding is tested in CI; its first scheduled sweep lands with the
    lifecycle soak (the recreate at 21:35Z restarted its 24 h interval).
  - Disarm: `$C stop witness`, remove both .env lines, then `$C up -d
    --no-deps --no-build lifecycle`.
- **Phase D + X3 DEPLOYED on both estates, 2026-09-14** (commits 4b8b352, 3909826,
  8f1c0df; CI green on every job incl. the compose-smoke gateway roundtrip and the
  compose-upgrade-smoke throttle flow).
  - **Build:** five parallel module builders (D1 to D5), each reviewed and fixed;
    one verifier (9/10 CLOSED); an integration workflow applied ~48 held-back
    edits plus Don's decisions, the D3b fixture fixes, OSFI `check-file` and X3.
    Its review found 2 BLOCKER + 2 FIX-FIRST + 3 NIT; all fixed; re-verify 8/8
    CLOSED. Local tools/tests: 418 passed, 6 skipped.
  - **Don's decisions 2026-09-13:** (1) meter log-only ALLOWs from steps 1-4
    too; (2) OSFI manual `check-file` path; (3) crosswalk daily egress yes;
    (4) Anthropic keys placed by Don (GB10 `.env`; Fly import, now Deployed).
  - **Disk incident:** C: on rog-command hit 0 bytes during the module workflow
    and every tool failed. Fixes: 24 orphaned test processes stopped; ~600 temp
    + 35 scratch dirs moved to `D:\claude-temp-archive\` (nothing deleted); test
    temp now goes to D:.
  - **GB10 deploy** 04:20Z (after vt's 04:05Z run passed): pre-phase-d images
    saved; verified quiesced backups (647 events, 2 segments); 15 containers;
    health 51/51 (perimeter + build sha); continuity 3/3; 0 restarts. One proxy
    log line was a connection refused to the console during the recreate.
  - **Fly deploy:** image `v1-2-d-8f1c0df` smoked first (51/51, 854 MiB);
    snapshot; release v8; health 51/51, continuity 3/3 to 255. Service
    processes carry `FIELD_CROSSWALK_EVERY=86400`, `FORCE_GATEWAY_URL` and
    `FIELD_FEDERATION_URL`.
  - **D-gate results (GB10 and Fly, identical):**
    - canary manifest reinstalled + re-provisioned: `rate_limits` 1 enforced;
      throttle 3 × ALLOW then BLOCK `E.rate_limit` retry_after 3600 s;
    - A+B metering: one ALLOW ⇒ metered +1, self +0;
    - regwatch POST: osfi, eu, nist `baseline`; iso `no-source`; `last_check`
      set. **OSFI is reachable from both estates** (the 403 was laptop-only);
    - `/discover`: owner-reason candidate; the synthetic key is absent from the
      body; a typo'd field is 422;
    - federation on a labelled synthetic contract: outbound in-contract ALLOW
      with direction; off-peer BLOCK `F.peer`; contract deactivated afterwards;
    - gateway `mock: False`, key present (length/prefix only);
    - collateral passes with the synthetic federation events allowed.
  - **X3 + A6 on the GB10:** `COMPOSE_PROFILES=witness,x3`;
    `FIELD_KILL_ENDPOINT_ALLOWLIST=canary-agent`. `x3-check` 11/11: kill
    `x3-<nonce>` ⇒ endpoint called 200 + agent halted with the same nonce; the
    revive flips the registry, not the process; a drill confirmed the endpoint
    in 14.8 ms and restored the canary. The canary-agent was restarted
    afterwards (unhalted). Fly: nothing (D7).
  - **NOT passing / needs Don:**
    - (a) **Keyed gateway call** ⇒ Anthropic HTTP 400 "credit balance is too
      low" on both estates. Key and gateway work; the account needs API
      credits. Usage-attribution evidence waits on that.
    - (b) **OSFI false flag on the GB10 — CLEARED by Don Hagell 2026-09-14T10:34:22Z** (`regwatch status`: active []; history records the clear; served `/attest/pack` 200). Was: A `check-file` run on Don's
      browser-saved page, after the live fetch had set the baseline, reported
      `changed` (browser save ≠ server fetch) and flagged osfi-e23 STALE. Pack
      generation is blocked there until a named reviewer runs `crosswalk
      regwatch clear osfi-e23 --reviewed-by NAME`. Fly was not affected
      (check-file not run there).
    - (c) D1e live over-ceiling check not run (it posts real spend rows: Don's
      call).
    - (d) The ssl SKILL.md hook 2 still sends unattributed actions (re-upload
      is Don's).
    - (e) field-agent plugin 0.1.2: reinstall wherever installed.
    - (f) Every recreate restarted the lifecycle and witness intervals: first
      scheduled `swept_at` ≈ 2026-09-15 04:21Z (GB10) and 04:25Z (Fly).
- **Usage:** 143 sub-agents, about 12 M output tokens, 72 agent-hours;
  `tasks/usage-report-2026-09-13.md`. From here on (Don): fewer and cheaper
  agents, one reviewer per change set, Sonnet for sweeps.
- **Phase F session opened 2026-09-14 ~10:45Z — live state re-confirmed
  read-only on both estates before any change.** GB10: HEAD 8f1c0df, 16
  project containers up since the 04:21Z recreate, RestartCount 0 on every
  one; `estate_probe health --expect-perimeter --expect-build-sha 8f1c0df…`
  51/51; `continuity` 3/3 to the phase-d pin (647 / 348a55f5…), fresh pin 677 /
  9d81e6d2…; `regwatch status` active [] (the osfi-e23 clear by Don Hagell at
  10:34:22Z is in `history`); ledger/sentinel (enforce, judge off)/gateway
  (mock false)/attest all report the build sha; `/data/keys` holds only the
  anchor pair; canary-agent up, not halted, 4589 work ticks. Fly: release v8
  `v1-2-d-8f1c0df`, machine 817eedf971947d started, checks 3/3; in-machine
  health 51/51, continuity 3/3 to the D pin (255 / 8141b1f1…), fresh pin 264 /
  aee4fd53…; key present (len 108, prefix ok); regwatch active [], history [].
  Registered on the GB10: canary-gb10, canary-gb10-retired, smoke-agent
  (retired), ssl-invoicing-agent, ssl-timekeeping-agent, volatility-trader —
  no self-agents yet (F1 registers them). DOA roster: 3 grantor rows
  (`grantor`, `allowed_scope`, `max_ttl_days`, `active`); owners.csv: Don
  Hagell (+ alias), FIELD canary.
  - **Soak evidence, witness (A5) — LANDED on the GB10:** seven
    `anchor.remote{estate: fly}` events authored after the 04:21Z recreate, one
    per hour at :21 (05:21 … 10:21Z; Fly length 264 from 05:21Z on), i.e.
    scheduler-written anchors > start + `FIELD_WITNESS_EVERY`. Direction 2
    still logs "not live (D5)" every tick.
  - **Lifecycle scheduled sweep — NOT yet:** `/findings` `swept_at` is still
    2026-09-13T14:21:34Z (roster_size 2, orphans 0); the first scheduled sweep
    after the recreate is due ≈ 2026-09-15 04:21Z (GB10) / 04:25Z (Fly).
  - rog-command: 33 python.exe processes are all MCP servers (mouser, gx10,
    windows-mcp, hermes) from other sessions — no orphaned test harnesses.
    C: 4.2 GB free; D: 615 GB free. CI: 8f1c0df success; 53fd921 (docs) in
    progress at the time of reading.

- **Phase F code DEPLOYED on the GB10 (switches OFF), 2026-09-14 13:37–13:39Z,
  commit 19701f4** (`gb10-deploy.sh phase-f`): 16 pre-phase-f image tags saved;
  pin 684 / 155c24e7…, quiesced backups promoted (field-data + field-manifests);
  every container recreated; health 51/51 with `--expect-perimeter
  --expect-build-sha 19701f4…`; continuity 3/3; restarts 0 → 0; the one
  "error" log line is the proxy's connection-refused to the console during the
  recreate (as at Phase D). The script's "MISMATCH canary-agent" is a script
  artefact: its built-ids list is taken with `--profile witness`, which drops the
  x3 profile, so canary-agent had no expected id; the running container IS the
  freshly built `:latest` (79ddd14a7483). New topology verified: networks
  `field-platform_agents` (internal) + `_default`; canary-agent on `agents`
  ONLY, forcegw + sentinel dual-homed, proxy/attest default only; volume
  `field-platform_field-attest-keys` mounted at `/data/attest-keys` in attest
  (empty until the key). Health now: ledger `signing: off`, `appendable: true`,
  `require_signing: false`, `seal_algorithm: sha-256-chain`; gateway
  `enforce: false`, `tool_check: false`, `sentinel_url: http://sentinel:8004`;
  attest `signing: off`.
  - **Pre-arming F-gate on the canary (13:40Z, `gb10-fgate.sh` → `fgate_checks.py`):
    PASS 0 failures.** F2 health fields present; canary `/check` ALLOW ⇒ the new
    `conformance.allow` is unsigned (signing off); F4 served pack
    `signed: false`, no `signed_via`; F1 health `enforce: false`; the allowed
    canary call was FORWARDED (enforce off) and the upstream answered 400 "credit
    balance is too low" (D1 — the forward happened, attribution did not); kill
    200 / revive 200 / heartbeat `killed=false`; **egress proof from inside
    canary-agent: `api.anthropic.com:443` FAILED (gaierror), `proxy:8080` FAILED
    (gaierror), `forcegw:8009` CONNECTED, `killswitch:8005` CONNECTED**;
    collateral 3/3; canary token revoked 2/2; canary-agent recreated afterwards
    (not halted).
  - **Keys generated in-estate (13:40Z, `gb10-f-keys.sh`; files only, nothing
    armed):** `ledger-sign` on `field-keys` (fingerprint
    `2772b68b0710c4631791d48f49e6e7522e3e697ceafc4b7f73026e98dbf06009`) and
    `attest-sign` on `field-attest-keys` (fingerprint
    `afdaac832b5f392d145eee1cc964b87adf12ea28d4b929393e395b6a1d87ab09`), both
    0600 under umask 077; public PEMs exported to `~/field-backups/*-gb10.pub.pem`
    and copied to `C:/Users/donal/.field-local/backups/` where the fingerprints
    were recomputed from the DER and matched. Custody as the anchor keys
    (D9 — confirmed by Don 2026-09-14).
  - **CI 19701f4:** compose-smoke (enforcing roundtrip on `smoke-egress`),
    compose-upgrade-smoke (attest-keys mount check + the F2 fault path) and
    fly-image-smoke all SUCCESS by 13:41Z; the tests matrix followed.
  - **Don's decisions 2026-09-14 (question tool, ~13:45Z):** A7 go on the GB10
    now; A9 go after a clean ≥ 1 h A7 soak without asking again; D9 custody =
    the anchor-key pattern; Fly go after the GB10 soak and CI green, same order.
  - **CI 19701f4 GREEN on every job** (tests 3.11-3.14 by 13:43Z).
  - **A7 ARMED on the GB10, 14:02:36Z** (`gb10-a7-arm.sh`): pre-F2 unsigned
    count recorded = 694 (`~/field-backups/pre-f2-unsigned-count.txt`);
    `.env` += `FIELD_LEDGER_SIGN_KEY=/data/keys/ledger-sign.pem`,
    `FIELD_LEDGER_REQUIRE_SIGNING=0`; scoped ledger recreate; the ledger reads
    the key path; `/health` `signing: on`, `appendable: true`,
    `require_signing: false`, `key_fingerprint` == the recorded 2772b68b…,
    `seal_algorithm: ed25519-signed-chain`; C0 health 51/51. From the first
    append after 14:02:36Z every pre-F2 ledger image is unable to start on this
    ledger (fix-forward only). Soak until ≥ 15:03Z, then `gb10-a7-soak.sh`.
  - **A8 ARMED on the GB10, 14:03:39Z** (`gb10-a8-arm.sh`): `.env` +=
    `FIELD_ATTEST_SIGNER=Don Hagell (custodian, estate key — standing attestation)`,
    `FIELD_ATTEST_SIGN_KEY=/data/attest-keys/attest-sign.pem`; scoped attest
    recreate; `/attest/health` `signing: on`, the D10 signer, fingerprint ==
    the recorded afdaac83…; served `GET /attest/pack` `signed: true`,
    `signed_via: estate-key`; **verified OFF-BOX on rog-command** with the local
    public PEM copy (`attest verify … --pubkey C:/Users/donal/.field-local/
    backups/attest-sign-gb10.pub.pem` exit 0: "signed by Don Hagell (custodian,
    estate key — standing attestation) via estate-key"); one metric mutated in a
    copy ⇒ exit 1 "signature INVALID"; C0 health 51/51. Signed packs persist;
    disarm = delete the two lines and recreate attest.
  - **A10 preconditions DONE on the GB10, 14:05:49Z** (`gb10-a10-prep.sh`; the
    first run stopped at the sentinel's mint with `D.grantor` because the roster
    step used `docker exec` without `-i` — fixed, re-run): manifests
    `conformance-sentinel.yaml`, `force-gateway.yaml`, `compliance-crosswalk.yaml`
    installed into `field-manifests`; DOA roster row `Founder & CTO, Spin State
    Labs` added (4 rows; 13 scope entries, `llm.messages` included; `max_ttl_days`
    30); each self-agent provisioned via `lifecycle provision` (validate →
    register → cap USD 5/daily → mint 30 d; owner `Don Hagell, Spin State Labs`,
    domain `platform`) — permanent registry/ledger writes on the plan's
    authority (REVISION 2.1 "F1 additions"); the three token ids written to
    `integration/demo/.env` (never printed; len 36 each); sentinel, forcegw and
    crosswalk recreated with `FIELD_SELF_AGENT_ID` + `FIELD_SELF_TOKEN_ID` (both
    SET in-container); forcegw's token introspects `active: true`, agent
    `force-gateway`, `llm.messages` in scope; health 51/51; collateral 8/8 with
    the self-agents' own registry/mint events allowed. Enforce still 0. The
    three tokens expire 2026-10-14: schedule their renewal (open item).
  - **Phase F code DEPLOYED on Fly, 14:42–14:49Z, release v9, image
    `v1-2-f-19701f4`** (`fly-deploy-f.sh` + `fly-deploy-f-part2.sh`): build-only
    push with `--build-arg FIELD_BUILD_SHA` from a clean `git worktree` at
    19701f4; service-less smoke machine 807deebed44368: health 51/51 with the
    build sha, 859 MiB RSS, destroyed; volume snapshot scheduled; `fly deploy
    --image --ha=false`; machine 817eedf971947d v9, checks 3/3; in-machine
    health 51/51 `--expect-perimeter --expect-build-sha`, continuity 3/3 to the
    D pin (264 / aee4fd53…). Two traps on the way: `git worktree add` with a
    `/d/...` path created the worktree under `C:\d\` (removed); with
    `MSYS_NO_PATHCONV=1` every LOCAL path handed to `fly ssh sftp put/get` must
    be Windows-style (`D:/...`), or the Windows binary cannot find it (first
    smoke attempt failed on that and destroyed its own machine; production
    untouched). Switches on Fly: all off until its arming steps.
  - **Fly pre-arming F-gate on canary-fly (14:49:46Z, `fly-arm-f.sh fgate` →
    in-machine `fly-fgate.sh` → `fgate_checks.py`): PASS 0 failures** — the same
    rows as the GB10 (F2 health fields, unsigned allow with signing off, served
    pack unsigned, enforce false, forwarded call ⇒ upstream 400 credit balance,
    kill/revive/heartbeat), collateral 3/3, canary token revoked 2/2. No
    egress row on Fly (single container: no per-process egress control, (b)).
  - **Fly keys generated in-machine (14:49–14:50Z, `volume_admin.py keys
    generate --dir /data/keys`): `ledger-sign` fingerprint
    `77a46f39aba40b2af9d02ced1e32d651562186ec2add8daf30657339c40e5987`,
    `attest-sign` fingerprint
    `1ecfa256f88fcf67ab6535bdbd1de7a99b1a41191f86ca81b4ec28a5300ff5ad`; both
    0600; public PEMs fetched to `C:/Users/donal/.field-local/backups/*-fly.pub.pem`,
    fingerprints recomputed locally from the DER and matched. LIMIT: every
    process in the Fly container can read `/data/keys` (README).
  - **GB10 A7 SOAK CLEAN, 15:03:48Z** (`gb10-a7-soak.sh`): 702 events, 8 signed
    (every event since arming), 694 unsigned == the recorded pre-F2 count, no
    unsigned event after a signed one; in the ledger container `ledger verify
    --path /data/ledger/events.jsonl --event-pubkey <the OFF-BOX public PEM
    copied back>` exit 0 ("OK — chain intact over 702 events … signed 8
    unsigned 694 first_unsigned_index 0 first_signing_failed_index none
    first_unsigned_after_signed none"); 16 containers, 0 restarts.
  - **Fly A7 ARMED, 15:04:16–15:05:32Z** (`fly-arm-f.sh a7`): pre-F2 count on
    Fly recorded = 273 (`D:/claude-tmp/fly-f/pre-f2-unsigned-count.txt`);
    `fly secrets set FIELD_LEDGER_SIGN_KEY=/data/keys/ledger-sign.pem` (one
    restart); `/ledger/health` `signing: on`, `appendable: true`,
    `require_signing: false`, `key_fingerprint` == the off-box 77a46f39…,
    `seal_algorithm: ed25519-signed-chain`; in-machine continuity 3/3 to the D
    pin. Irreversible for pre-F2 images from the first signed event, as on the
    GB10. The restart reset Fly's lifecycle/witness intervals again.
  - **GB10 A9 ARMED, 15:05:59Z** (`gb10-a9-arm.sh`; Don's go of ~13:45Z "after
    the clean soak"): `.env` `FIELD_LEDGER_REQUIRE_SIGNING=1` (14 services see
    it); scoped ledger recreate; `/health` `signing: on`, `appendable: true`,
    `require_signing: true`; canary mint under REQUIRE_SIGNING ok; canary
    `/check` 5/5 with the new `conformance.allow` SIGNED; canary token revoke
    2/2 with the `delegation.revoke` SIGNED (no `signing_failed`); collateral
    3/3; C0 health 51/51. The fault path stays CI-proven only. Fly A9 after a
    ≥ 1 h GB10 A9 soak (≥ 16:06Z).
  - **Fly A8 ARMED, 15:09:44Z** (`fly-arm-f.sh a8`: `fly secrets import` of the
    D10 signer name + `/data/keys/attest-sign.pem`, one restart): `/attest/health`
    `signing: on`, signer `Don Hagell (custodian, estate key — standing
    attestation)`, fingerprint == the off-box 1ecfa256…; served pack fetched
    in-machine and **verified OFF-BOX on rog-command** with the local public
    PEM (exit 0 "via estate-key"); one metric mutated ⇒ exit 1; in-machine C0
    after the A7 restart 51/51 + continuity 3/3.
  - **GB10 A10 ARMED, 15:10:05Z** (`gb10-a10-arm.sh`): `.env`
    `FORCE_GATEWAY_ENFORCE=1`; scoped forcegw recreate; `/gateway/health`
    `enforce: true`, `sentinel_url http://sentinel:8004`, timeout 30 s; C0
    51/51; the sentinel's own passthrough identity (self id + A10 token, from
    inside the sentinel container) is ACCEPTED by the enforcing gateway and
    forwarded (upstream 400 credit balance — a 401/403 would have meant the
    self identity was refused). **F-gate `--enforce-armed` PASS 0 failures:**
    no headers ⇒ 401; allowed canary call forwarded ⇒ upstream 400 (D1);
    `x-field-action` out of scope ⇒ 403 `D.scope`; killed canary ⇒ 403
    `E.kill_switch` with `gateway.refused` 1 → 2; revive 200; heartbeat
    `killed=false`; egress proof unchanged; canary token revoked; canary-agent
    recreated. Collateral first reported the two `gateway.refused` events
    (authored `force-gateway`) as unintended — an allow-list omission in the
    gate script, fixed (`force-gateway:gateway.refused|gateway.shadowed`) and
    re-run for the same window: 3/3.
  - **GB10 A11 ARMED, 15:10:57Z**: `.env` `FORCE_GATEWAY_TOOL_CHECK=1`; scoped
    forcegw recreate; `/gateway/health` `tool_check: true`,
    `tool_check_active: true`; C0 51/51. Stage 2 is NOT live-verifiable until
    the account has API credits (D1): keyless, config visible in health only.
  - **GB10 arming COMPLETE (A7–A11) at 15:11Z; every switch armed one per
    recreate with a canary check between.** Real callers unaffected by A10/A11:
    the ssl skills and vt never call the gateway; judges are off (D14).
  - **Fly A10 preconditions DONE, 15:13–15:14Z** (`fly-a10-prep.sh` → in-machine
    `fly-a10-prep-inmachine.sh`): the three packaged self-manifests copied to
    `/data/manifests/<id>.yaml`; DOA roster row `Founder & CTO, Spin State Labs`
    added (13 scope entries incl. `llm.messages`, `max_ttl_days` 30); each
    self-agent provisioned (validate → register → cap → mint 30 d; owner `Don
    Hagell, Spin State Labs`, domain `platform`); the three token ids fetched to
    a 0600 local file and `fly secrets import`ed (one restart), the file deleted,
    values never printed; secrets list shows 3 `*_SELF_TOKEN`; health 51/51 with
    the build sha; a /proc scan in-machine shows `FIELD_SELF_AGENT_ID` +
    `FIELD_SELF_TOKEN_ID` SET on the sentinel, forcegw and crosswalk processes
    only (registry: none); the gateway's token introspects `active: true` with
    `llm.messages`. Enforce still 0. The three Fly tokens expire 2026-10-14
    (renewal open item, with the GB10's).

**Phase F BUILT — committed locally, NOT deployed, NOT armed (2026-09-14, session
ae3d31d1).** Three parallel builders on disjoint files (F2 ledger + field-core +
sentinel; F1 gateway + field-core llm + self-manifests; F4 attest), ONE reviewer
each (medium depth, mutation-checked every guard the arming rows rest on, small
fixes inline, no fixer round), then a serialized integration step by the
orchestrator and one Sonnet verifier over the full suites and demos. Commits:
3f82811 (F2), 5ae3600 (F1), b648118 (F4), 5b183c1 (integration). F2b (per-service
caller keys on the GB10) is a second-wave build after the F deploy; its brief is
written. Plan text followed; deviations, each with the reason:
- `ledger verify --event-pubkey` is a NEW flag: the plan said "`--pubkey`
  (existing flag)" but REVISION 2.1 made the anchor key and the per-event sign
  key separate keys, so one flag cannot verify both. `--pubkey` stays the
  anchor key.
- `compute_event_hash` pops `signature` exactly as it pops `hash` (one line):
  hash first, sign second; the hash of every existing event is unchanged
  (pinned by a pre-F2 fixture test). Both new event fields (`signature`,
  `signing_failed`) are OMITTED from serialized lines when None, so a pre-F2
  image parses every unsigned line and the reversibility promise "image
  rollback until the first signed event" holds (reviewer re-proved it against
  the HEAD `LedgerEvent` class on raw bytes).
- Gateway→sentinel timeout default 30 s (above the sentinel's 22 s structural
  budget, test-pinned); a judge-on sentinel needs 60 s — recorded as an A12
  precondition instead of raising the default.
- CI compose-smoke provisions `smoke-egress` (with a manifest) for the
  enforcing roundtrip and keeps the manifest-less `smoke-agent` step for
  `BLOCK I.manifest`.
- F4's key is on its OWN volume (`field-attest-keys`, attest-only mount,
  `attest-keys-admin` writer), not on `field-keys` as the resolved table said:
  the gb10 override header already required an attest-only mount.
- Root README has no "row 40"/"row 68": the Declared/Enforced wording lives in
  the service READMEs (sealed-ledger, force-gateway, spend-governor,
  attestation-reporter); E1 will cite them.
What shipped, with the evidence the reviewers produced themselves:
- **F2.** `FIELD_LEDGER_SIGN_KEY` + `FIELD_LEDGER_REQUIRE_SIGNING`; every write
  path gated (`append`, rotation, hold place/release, retention apply);
  `/health` `appendable`/`signing`/`key_fingerprint`/`seal_algorithm`/
  `require_signing`/`key_error`; stop-type list exactly `delegation.revoke`,
  `kill.*`, `lifecycle.decommissioned` (stamped `signing_failed: true` INSIDE
  the hash); sentinel: `appendable: false` counts as unreachable, and in
  enforce mode a failed ALLOW record is BLOCK `L.unreachable` and never metered
  (log-only unchanged, documented). Reviewer: re-linked tamper by hand (plain
  verify exit 0, `--event-pubkey` exit 1 naming index 1); `/hold/release`,
  `/retention/apply`, `/rotate` all 503 when not appendable (judged acceptable:
  a hold that cannot be released keeps data); sign cost 0.13 ms; one latent
  disclosure fixed (`SigningConfig` repr no longer shows the PEM). Suites:
  root group 605 passed 3 skipped; sentinel 101 passed.
- **F1.** `FORCE_GATEWAY_ENFORCE=1`: identity + authority fail closed at the
  egress BEFORE passthrough and BEFORE the bypass window; 401 / 403 / 503
  contract; `gateway.refused` on every refusal; passthrough exemption only for
  the three self ids; stage 2 (`FORCE_GATEWAY_TOOL_CHECK=1`) strips
  out-of-scope `tool_use`; `field_core.llm` sends the self pair only toward
  `FORCE_GATEWAY_URL`. Reviewer: six mutations all caught; traced every branch
  — no header combination reaches the upstream without a sentinel ALLOW;
  `x-field-token` never logged, ledgered or echoed; token bound to the agent
  (A's token with B's id ⇒ 403 `D.token`, proven on the in-process stack).
  Residual: the no-recursion guarantee for a sentinel judge call rests on the
  sentinel's token AND manifest carrying `llm.messages` exactly (now true for
  all three self-manifests). Open: double metering of self-agent passthroughs
  when judges are on (over-count, conservative; judges off; F3 owner).
  Suites: gateway 182 passed; crosswalk 154 passed 1 skipped.
- **F4.** Served packs signed under `FIELD_ATTEST_SIGNER` with
  `signed_via: estate-key` inside the signed bytes; unset / one-of-two / bad
  key ⇒ UNSIGNED and health says why, never a process exit. Reviewer: OLD code
  signs → NEW verifies and NEW CLI signs → OLD verifies (both pass); `/health`
  `key_error` redacted to the basename (it disclosed the key's directory on an
  open route). Suite: 65 passed.
- **Integration (5b183c1).** Compose/entrypoint passthroughs for every new
  variable (the GB10 sentinel's restated block stays its FULL env, test-pinned);
  GB10 `agents` internal network (canary-agent alone; forcegw dual-homed;
  sentinel, killswitch, delegation, governor, ledger attached); CI: compose-smoke
  enforce=1 roundtrip, compose-upgrade-smoke attest-keys mount check + the F2
  fault path (A9 is CI-proven, never live); runbook §4 "Phase F additions";
  F3 reword. Local: test_deploy_docs 21 passed after re-pinning the two
  entrypoint serve lines (they now carry per-process self identities).
- **Not built here (by design):** the estates still run enforce 0 / signing off
  / attest unsigned until A7–A11; keyed evidence (allow-and-forward 200, F3
  usage attribution, stage 2 live) waits on Anthropic credits (D1); F2b.
- **Verifier (Sonnet, foreground, full sweep):** every service suite green
  (field-core 166; sealed-ledger 440 + 3 skipped; delegation 81; governor 80;
  kill-switch 75; fedbroker 87; registry 168; sentinel 101; replay 74; crosswalk
  154 + 1; gateway 182; lifecycle 125; attest 65; console 11; field-agent 74),
  all five demos exit 0 (capstone `run_demo.sh` 33 s), `verify_sync.sh`
  "templates in sync", ci.yml/fly.toml parse, entrypoint LF, `git diff --check`
  clean, no secret literal in the diff. Its 57 `tools/tests` failures were an
  environment artifact: `powershell.exe` cannot initialise a runspace under the
  temp dir it chose ("InitialSessionState threw an exception"), so every test
  that shells out to PowerShell (`test_field_rest_secret.py`, `test_ssl_renewal.py`,
  and three `test_renew_token.py` leak cases whose captured output was the
  PowerShell failure text) failed. Re-run by the orchestrator under a temp dir
  PowerShell accepts: `test_field_rest_secret.py` + `test_ssl_renewal.py` 59
  passed, the `never_prints` cases 4 passed. Net: the full tree is GREEN
  (1,776 + 63 passed, 12 skipped, 0 real failures).
- **Agents:** 1 explore + 3 builders + 3 reviewers + 1 verifier (Sonnet); the
  per-agent tokens are in `tasks/agent-usage.md`. Two agents stopped early to
  "wait for a background run" and were resumed with a message — a pattern to
  brief against next time.

**Phase D BUILT — uncommitted, NOT deployed (2026-09-13).** Five builders
(D1–D5), per-stream review and fix, three integrators, an integration review
and its fix round. Plan items and D-gate adds: `tasks/todo.md` Phase D.
Don's decisions of 2026-09-13, applied: (1) the sentinel meters EVERY ALLOW in
either mode, a log-only shadow decided at steps 1-4 included; (2) OSFI is read
manually, `crosswalk regwatch check-file`; (3) crosswalk egress yes,
`FIELD_CROSSWALK_EVERY=86400` on both estates; (4) the ANTHROPIC_API_KEY is
Don's to place, and no key was added.
- **D1 throttle + metering.** Options A + B. The governor migration RUNS AT
  OPEN, so image rollback is clean only until the D1 governor first starts
  on the persisted `spend.sqlite3` (runbook reversibility table; data-step
  down-migration there). Deploy spend-governor with or before the sentinel:
  a D1 sentinel in front of a pre-D1 governor ledgers `sentinel.metering_gap`
  on every ALLOW and gets no throttle. `lifecycle provision` now loads
  `rate_limits` after the cap (a failed step mints nothing).
- **D1e, built end to end in the integration fix round.** delegation-authority
  stamps the matched DOA roster row's `max_spend_usd` on the token (side table
  `token_spend_ceilings`, created at open; a pre-D1e image still mints and
  revokes on the file) and `/introspect` returns it with `issued_at`; the
  sentinel BLOCKs `E.spend_cap` at it. CI-proven (no monkeypatch). Live, it
  needs `FIELD_DOA_ROSTER` armed and a roster row carrying `max_spend_usd`;
  the generated roster sets none, so nothing on the estates changes until one
  is added. Additive token JSON: the key appears only when a ceiling is stamped.
- **D2 gateway.** On each estate's next deploy `/gateway/health` flips
  `mock: true` → `mock: false` and `POST /v1/messages` answers 502 naming
  ANTHROPIC_API_KEY until Don places the key. With FORCE_GATEWAY_URL
  estate-wide, a judge-on sentinel or crosswalk depends on forcegw holding the
  key (keyless ⇒ JudgeError ⇒ `D.semantic` escalation). `gateway.passthrough`
  payload is `{client_host, agent_id}`; an agent calling with
  `x-force-passthrough` and its agent id is still metered. Evidence as the D2
  fixer reported it: gateway 115 passed; 24 single + 4 compound mutants, 0
  survivors after one added test; demo.sh 11 s.
- **D4 regwatch.** Readings are anchored: a 200 page naming none of a URL's
  cited reference identifiers (bot challenge, soft 404, moved page) is
  `unreachable` ("anchor missing"), on the official EU URL falling back to
  the mirrors; a rewrite that drops every cited identifier also reads
  unreachable and needs a manual set-stale. Live 2026-09-13 from the build
  laptop: EUR-Lex ELI 200 (1.5 MB, via official), NIST 200, both mirror pages
  200 and anchored; OSFI 403 to the honest User-Agent, hence Decision 2. The
  store lock is a zero-byte sidecar, `crosswalk_stale_flags.json.lock`. Exit 0
  from `regwatch check --fetch` or `check-file` means no NEW change, not all
  clear (`STALE (standing):` on stderr). After a manual OSFI baseline,
  `/staleness` `last_check` still shows osfi `unreachable`; the evidence is the
  stored reading (`regwatch check` without `--fetch`: `stored_via:
  manual:<NAME>`, `file_sha256`).
- **Needs decision / action by Don:**
  - Token bursts: any agent whose usage policy sets `token_rate_limit` is
    THROTTLED on every `/status` during a burst, so an enforcing sentinel
    BLOCKs ALL its checked actions `E.rate_limit` until the window ages out,
    and resolving the rogue_burst escalation no longer lifts it.
    `plugins/field-agent/templates/bootstrap_operator.py:87` installs
    `token_rate_limit: 200_000` for every plugin-bootstrapped agent. Check the
    estates' policies before flipping enforce.
  - SSL skills hook 2: `agents/ssl-*/SKILL.md` still pass an unattributed
    `-Actions <n>` (invoicing :23, timekeeping :21). On a D1 governor those
    self-reports add to the sentinel-metered count toward `action_limit`
    totals. Harmless today (the ssl manifests set only a USD spend_cap). At the
    next skill re-upload, and before any `action_limit` is added, make hook 2
    cents-only (drop `-Actions`). Deferred now because a SKILL.md edit forces a
    re-upload.
  - A3 `PackRequest` optionality by `agent_id`: plan-assigned to D4, not
    built. Build it as a D4 follow-up or move it to a named later item.
  - The field-rest.ps1 pin in `docs/runbooks/token-renewal.md` §5.2 was
    re-pinned to `412d1352…` for the D1 hook 2 change; re-run the §5.2
    `Get-FileHash` precondition before the next live renewal.
  - D-gate D1e row: arm the roster with a `max_spend_usd` row for the canary
    grantor, then re-provision the canary, before that row can run.

### Previous phase (context)
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
on record) [superseded v1.2 D4: regwatch content-change detection (normalised
text, not semantics); the EUR-Lex "limit" was the 2026-08-09 agent's fetch
tool, and httpx read the ELI URL 200 / 1.5 MB on 2026-09-13; OSFI answers 403
to the crosswalk User-Agent and is read manually via `regwatch check-file`] — the enforcement is code, the cadence is a process commitment;
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
composed service. [SUPERSEDED 2026-09-12 by A0: composed and routed at
/crosswalk; the CLI remains the canonical path for packs.] Stop with: `docker compose ... down` (same two -f files).
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
  [2026-09-13: that was the session agent's fetch tool, not EUR-Lex; httpx
  read the ELI URL 200 / 1.5 MB. The manual article check is still open.]

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
  stale, no re-vendor needed. Re-vendored 2026-09-12 from Force-Field
  d841c25 (`field` 1.1.0 gate keys): schema blob 8e03961 identical in all
  three copies, templates byte-identical, verify_sync.sh green — see the
  Enforcement Gate section at the top.

## Next action (remaining backlog, in rough priority)
(Items "push to GitHub" and "record capstone video" removed 2026-08-29 —
both verified done earlier in this file: Remote section 2026-08-09,
Capstone video section 2026-08-10.)
1. Deployment (private first): GB10 proxy cutover DONE 2026-09-08 (:18080).
   Still open: Cloudflare Tunnel or Tailscale Serve in front of :18080 with
   FIELD_SHARED_SECRET ON (the GB10 estate currently has NO shared secret —
   LAN-trust only). Netlify gets ONLY the static tier.
   Rebuild GB10 (636e4bb) + Fly (e07cd5b) at ≥1727de0 before any gate-key
   manifest is registered on either estate (pre-lockstep field-core →
   `I.manifest` BLOCK in enforce until then).
2. Real-agent dogfood STARTED 2026-09-08 in ENFORCE (ssl-timekeeping-agent,
   ssl-invoicing-agent). The 2-week log-only burn-in / 30-day false-block
   window is NOT running by decision; revisit if the ADR 02 gate is needed.
   Next: first real governed runs of both skills; token re-mint before
   2026-10-08; decide whether the daily 6 pm timekeeping draft should
   post its own `/spend` from a scheduled task.
3. Manual EUR-Lex cross-check of EU AI Act Art. 12 + 14 (a human reads the
   articles; the old "fetch tooling can't" was the 2026-08-09 agent's tool —
   httpx reads the page, and v1.2 D4 regwatch watches it for content change);
   purchase + ingest ISO/IEC 42001.
4. Schedule `ledger anchor` (Task Scheduler/cron) with the anchor file
   shipped off-box; evaluate OpenTimestamps publication of anchor records.
5. Signing-key rotation/revocation; per-caller identity; TLS via proxy
   (the compose proxy exists now; TLS/identity land at the tunnel/edge).
6. Enhancements: sentinel verdict-write durability, ledger read index,
   `attested_at` for lifecycle, gateway streaming, telemetry persistence,
   ops-console pagination/push, quarterly pack archive convention,
   verify_sync.sh into CI.
7. Enforcement Gate follow-ups (2026-09-12): bump field-agent plugin.json
   0.1.1 → 0.1.2 (+ source commit in the SOURCES.md stamp, `claude plugin
   validate`); reword field-agent README/SKILL/command "design-time only";
   crosswalk controls for irreversible_actions / protected_paths /
   tool_call; one live Windows Git-Bash gate run + one PowerShell-fallback
   run after `claude auth login`; watch Force-Field Gate v1.2
   `kill_switch.local_sentinel` — the next lockstep.

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
