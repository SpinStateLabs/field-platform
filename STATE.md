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
daily egress network policy (D4); FORCE_GATEWAY_URL estate-wide (D2e);
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
- **Usage:** 143 sub-agents, about 12 M output tokens, 72 agent-hours;
  `tasks/usage-report-2026-09-13.md`. From here on (Don): fewer and cheaper
  agents, one reviewer per change set, Sonnet for sweeps.

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
