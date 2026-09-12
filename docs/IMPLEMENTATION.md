# FIELD Platform — Implementation & Operations Guide

How to install, run, verify, and operate the platform, and how to put a new
agent under governance. Companion to [ARCHITECTURE.md](ARCHITECTURE.md);
current status always lives in [STATE.md](../STATE.md).

## 1. Prerequisites

- Python ≥ 3.11 (built and tested on 3.14; deps: pydantic v2, FastAPI,
  uvicorn, httpx, Typer, PyYAML, cryptography — all wheel-installable on
  x86_64 and aarch64).
- Git Bash on Windows (demo scripts are bash). No Docker needed locally.
- Optional: any Linux box with Docker + Compose v2 for the container path
  (verified on the GB10/DGX Spark). Netlify and similar static/serverless
  hosts **cannot** run this — they don't run containers.

## 2. Install from a clean checkout

Keep the venv **outside** any synced folder (Google Drive sync fights
SQLite and per-file churn):

```bash
python -m venv ~/.venvs/field-platform
source ~/.venvs/field-platform/Scripts/activate   # Windows Git Bash
pip install -e "packages/field-core[dev]"
for s in sealed-ledger agent-registry delegation-authority spend-governor \
         kill-switch conformance-sentinel incident-replay \
         compliance-crosswalk force-gateway federation-broker \
         lifecycle-manager attestation-reporter; do
  pip install --no-deps -e "services/$s"
done
# --no-deps: field-agent depends on conformance-sentinel (not on PyPI);
# everything it needs is already installed above.
pip install --no-deps -e "packages/field-agent"
pip install fastapi uvicorn httpx pytest
```

Verify (expected: 209 passing as of the field-agent gate). Two steps — the
second group's tests import their local `tests/conftest.py`, so run them
from inside each package with `python -m pytest` (CWD on sys.path):

```bash
pytest packages/field-core/tests services/sealed-ledger/tests \
  services/agent-registry/tests services/delegation-authority/tests \
  services/spend-governor/tests services/kill-switch/tests \
  services/federation-broker/tests
for s in conformance-sentinel incident-replay compliance-crosswalk \
         force-gateway lifecycle-manager attestation-reporter ops-console; do
  (cd "services/$s" && python -m pytest -q tests)
done
(cd packages/field-agent && python -m pytest -q tests)
```

> Windows note: consoles default to cp1252 — every CLI forces UTF-8 stdout.
> Write files with CLI flags (`--out`, `--markdown`), not shell redirects.

## 3. Environment reference

| Variable | Default | Purpose |
|---|---|---|
| `FIELD_DATA_DIR` | `./var` | Root for every service's store |
| `FIELD_REGISTRY_URL` | `http://127.0.0.1:8001` | agent-registry |
| `FIELD_LEDGER_URL` | `http://127.0.0.1:8002` | sealed-ledger |
| `FIELD_DELEGATION_URL` | `http://127.0.0.1:8003` | delegation-authority |
| `FIELD_SENTINEL_URL` | `http://127.0.0.1:8004` | conformance-sentinel |
| `FIELD_KILLSWITCH_URL` | `http://127.0.0.1:8005` | kill-switch |
| `FIELD_GOVERNOR_URL` | `http://127.0.0.1:8006` | spend-governor |
| `FIELD_REPLAY_URL` | `http://127.0.0.1:8007` | incident-replay |
| `FIELD_CROSSWALK_URL` | `http://127.0.0.1:8008` | compliance-crosswalk (served since v1.2 A0) |
| `FIELD_GATEWAY_URL` | `http://127.0.0.1:8009` | force-gateway |
| `FIELD_FEDERATION_URL` | `http://127.0.0.1:8010` | federation-broker |
| `FIELD_LIFECYCLE_URL` | `http://127.0.0.1:8012` | lifecycle-manager (served since v1.2 A1) |
| `FIELD_ATTEST_URL` | `http://127.0.0.1:8013` | attestation-reporter (served since v1.2 A2) |
| `FIELD_MANIFEST_DIR` | `.` | Base for relative `manifest_ref` paths (compose/Fly: `/data/manifests`) |
| `FIELD_LIFECYCLE_ROSTER` | *(unset)* | Owner roster CSV for the lifecycle scheduler; unset ⇒ ticks logged as skipped |
| `FIELD_LIFECYCLE_EVERY` | `0` (off; compose/Fly `86400`) | Seconds between lifecycle sweeps |
| `FIELD_CROSSWALK_EVERY` | *(unset; compose/Fly `86400`)* | Seconds between crosswalk runs — passthrough only until D4 lands the scheduler |
| `FIELD_DOA_ROSTER` | *(unset)* | Delegation-of-authority roster (**YAML**, see `manifests/doa-roster.example.yaml`). Read by delegation-authority since v1.2 B1; unset = gate off. Set = **fail-closed**: an unreadable or invalid roster makes every mint 503 |
| `FIELD_KILL_ENDPOINT_ALLOWLIST` | *(unset)* | Comma-separated hosts the kill-switch may signal. Read by kill-switch since v1.2 B3; unset = no endpoint is ever called. Gates the **host**, not the path or method |
| `FIELD_LEDGER_RETENTION_DAYS` | *(unset; compose/Fly `2555`)* | Ledger retention floor — passthrough only until C2 reads it |
| `FIELD_ORG_NAME` | `Spin State Labs` | Home org for federation checks |
| `FIELD_SHARED_SECRET` | *(unset)* | Set everywhere to require `x-field-auth` |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_BASE_URL` | *(unset)* | force-gateway real upstream (never in the repo) |
| `FORCE_GATEWAY_MOCK=1` | — | Deterministic upstream, no key needed |

The defaults above are the local no-docker path. Against the compose stack
(single published proxy port, `integration/demo/Caddyfile`) point each URL
at its path prefix instead: `FIELD_REGISTRY_URL=http://localhost:8080/registry`,
`.../ledger`, `.../delegation`, `.../sentinel`, `.../killswitch`,
`.../governor`, `.../replay`, `.../gateway`, `.../federation`,
`.../lifecycle`, `.../attest`, `.../crosswalk`
(GB10 publishes 18080; the ops-console dashboard is the proxy root `/`).

Boot order when starting by hand: registry + ledger → delegation +
governor → sentinel + kill-switch → replay, forcegw, fedbroker, console →
crosswalk (:8008), lifecycle (:8012), attest (:8013). (Each `<cli> serve
--port N`; CLIs: `registry ledger delegation governor killswitch sentinel
replay crosswalk forcegw fedbroker lifecycle attest field`.)

## 4. Fastest proof it works

```bash
bash integration/demo/run_demo.sh
```

~23 s: boots seven services, validates + registers the demo agent, mints,
drafts under governance, escalates at the spend threshold, blocks the rogue
action, runs a timed kill drill, writes the RACI post-mortem, renders the
board pack. Artifacts land in `integration/demo/out/`. Each service also
has its own `<service>/demo.sh` (<60 s each).

## 5. Container path (verified on the GB10)

```bash
cd integration/demo
docker compose build && docker compose up -d
# smoke (single proxy port; per-service ports are not published):
#   for p in registry ledger delegation sentinel killswitch governor replay \
#            gateway federation lifecycle attest crosswalk; do
#     curl -sf localhost:8080/$p/health; done; curl -sf localhost:8080/health
docker compose down
```

Verified 2026-08-08 on the DGX Spark (aarch64): all nine services healthy;
sentinel correctly returns BLOCK `I.manifest` for an agent with no manifest
in the container — mount manifests and set `FIELD_MANIFEST_DIR` for real
use. GB10 staging copy: `/home/spinner/field-platform-verify/` (images left
in place). x86_64 compose run still pending (CI candidate).

## 6. Putting a NEW agent under governance (the core workflow)

1. **Manifest** — start from a shipped template and resolve every
   REPLACE-ME:
   ```bash
   field templates --show default --out manifests/my-agent.yaml
   field validate manifests/my-agent.yaml     # must be VALID, not just parse
   ```
2. **Register** (human owner is mandatory):
   ```bash
   registry add my-agent --name "My Agent" --owner "Jane Doe, Controller" \
     --domain finance --manifest-ref manifests/my-agent.yaml
   ```
3. **Cap** its spend from the manifest:
   ```bash
   governor set-cap my-agent --from-manifest manifests/my-agent.yaml
   ```
4. **Mint** its authority (a human grants; scoped; expiring):
   ```bash
   delegation mint my-agent --granted-by "Jane Doe, Controller" \
     --scope "read timesheets" --scope "draft invoices" --ttl 3600
   ```
5. **Wrap the code** — the front door is the `field-agent` SDK
   (`docs/INTEGRATION.md` has the full guide):
   ```python
   from field_agent import FieldAgent, ActionBlocked, ActionEscalated, AgentKilled

   agent = FieldAgent("my-agent", token_id=lambda: current_token_id(),
                      heartbeat_max_age=30.0)

   @agent.governed("draft invoices")
   def draft_invoice(row): ...
   # BLOCK raises ActionBlocked BEFORE the body runs; ESCALATE raises
   # ActionEscalated (item is already in the human queue).

   agent.report_spend(cents=1200, actions=1)             # operating cost
   agent.report_usage_from(llm_response)                 # LLM tokens, priced
   agent.ensure_alive()                                  # raises AgentKilled
   ```
   (`@governed` from `conformance_sentinel.governed` remains the low-level
   form — the SDK re-exports it unchanged.) For observed rather than
   self-reported token metering, route LLM calls through the gateway
   (`ANTHROPIC_BASE_URL=http://127.0.0.1:8009`, header
   `x-field-agent-id: my-agent`).

## 7. Security switches

- **Authn:** generate a secret
  (`python -c "import secrets; print(secrets.token_urlsafe(32))"`), export
  `FIELD_SHARED_SECRET` in *every* service and client environment. All
  endpoints except `/health` then require `x-field-auth`. Unset = demo mode.
- **Federation signing:** `fedbroker keygen` (private key never enters a
  repo) → counterparty GC registers your public key on their contract →
  `fedbroker sign --manifest m.yaml --key private.pem` → pass
  `--signature` on crossings. Contracts with a registered key refuse
  unsigned/tampered manifests.

## 8. Scheduled operations

| Cadence | Command | Notes |
|---|---|---|
| Weekly | `lifecycle sweep --roster owners.csv --markdown sweep.md` | exit 3 = findings → alert. `owners.csv` is HR's export (`owner` column). Auto-kill only ever with `--auto-kill-orphans` |
| Quarterly | `attest render --out packs/2026-Q3 --period "Q3 2026"` | archive each pack — they are point-in-time evidence |
| Quarterly | `crosswalk run manifests/*.yaml --agent-id <id> --markdown` | declared-vs-evidenced coverage with live evidence |
| Ad hoc | `killswitch drill <agent> --operator "CISO"` | keep the 2 a.m. answer measured |
| Ad hoc | `replay run <agent> --since ... --until ... --markdown pm.md` | incident post-mortem |

Windows Task Scheduler: point at
`C:\Users\donal\.venvs\field-platform\Scripts\lifecycle.exe` with args.

## 9. What is left to do (as of 2026-08-08)

**Capstone-facing**
1. Record the demo video off `run_demo.sh` (evidence docs in
   `docs/capstone-evidence/` are the written narrative).
2. Push the repo to a remote (currently local-only git).

**Compliance follow-through**
3. Cross-check the two EU AI Act citations against EUR-Lex
   (CELEX:32024R1689) — currently verified via the AI Act Explorer mirror.
4. Purchase and ingest ISO/IEC 42001; populate its citations (the guard
   test blocks citing it until then).

**Engineering hardening**
5. CI: GitHub Actions matrix (py 3.11–3.14) + an x86_64 compose run.
6. Signing-key rotation/revocation; per-caller identity beyond the shared
   secret; TLS via fronting proxy for any non-local deployment.
7. Known-gap backlog: registry writes as ledger events, sentinel
   verdict-write durability, ledger read index, `attested_at` field,
   force-gateway streaming, telemetry persistence, outbound federation
   gating, retention enforcement.

Nothing in this list blocks using or demonstrating the platform.
