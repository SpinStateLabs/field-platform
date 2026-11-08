# FIELD Platform

Reference implementations of 12 enterprise AI-governance systems grounded in
the **Force Field Protocol**: **FORCE** (runtime prompt protocol — Forbid
flattery · Oppose premise · Reference sources · Chain-of-thought · Express
uncertainty) and **FIELD** (design-time governance — Federation · Identity ·
Enforcement · Ledger · Delegation).

Built by Spin State Labs (Waterloo, ON). Humans organize; AI operates.
Simultaneously Spin State's product line and the University of Waterloo
AI-CTO capstone initiative.

## The honesty line

FIELD v1.0 (the shipped Claude Code plugin) **declares** governance in a
manifest. This platform is what makes it **enforced**. Every service README
carries an *Enforced vs. Declared* table stating exactly which guarantees are
enforced in code and which are declarations awaiting infrastructure. A
governance product that overclaims has already failed.

## Layout

```
field-platform/
  STATE.md                  # current phase, last milestone, next action — read this first
  packages/field-core/      # single source of truth for all schemas
  packages/field-agent/     # client SDK: governed actions, usage metering, heartbeat halt
  services/<system>/        # 14 service directories: the 12 systems below plus ops-console and claude-approver
  integration/demo/         # docker-compose end-to-end scenario (capstone centerpiece)
  defence-shield/           # agent-incident-retro: offline web-log review that flags rogue-agent incidents (own test suite)
  tools/                    # operator CLIs and verifiers: estate_probe, phase_g_check, topology_lint, ...
  agents/                   # reference agent definitions (the two SSL agents)
  manifests/                # FIELD governance manifests for those agents and services
  plugins/                  # packaged plugins (field-agent)
  .claude-plugin/           # plugin marketplace manifest
  docs/                     # including ARCHITECTURE, IMPLEMENTATION, INTEGRATION; adr/ (decisions),
                            #   runbooks/, capstone-evidence/ (phase-gate evidence artifacts)
  tasks/                    # working notes and lessons
  .github/workflows/        # CI
  CHANGELOG.md  ROADMAP.md
```

## The 12 systems

The one-liner column is the public wording. Every word in it is test-backed (Enforced) or labelled Declared in [docs/capstone-evidence/v2-one-liners.md](docs/capstone-evidence/v2-one-liners.md); `python tools/check_one_liners.py` checks each Enforced citation exists. Estate status is recorded outside this repository and is Declared for every row; nothing here is a compliance or certification claim.

| # | System | FIELD letter | Exec owner | Phase | One-liner |
|---|--------|--------------|-----------|-------|-----------|
| 1 | agent-registry | Identity | CIO | 1 | A register of agents (one record per unique agent id, a non-empty human owner string, and a manifest reference that must resolve to a valid manifest when one is set at registration) with discovery of unregistered shadow-agent candidates from supplied artifacts: service-account CSVs, an n8n workflow export, and API-key scans (file-based, heuristic). |
| 2 | sealed-ledger | Ledger | CFO/audit | 1 | A tamper-evident record of events appended by estate services: hash-chained, Ed25519-anchored; estate-level retention by segment rotation (mechanism; rotation is not armed by default - key custody undecided); an offline-re-verifiable export (a served export is unsigned); per-event ledger-signed when FIELD_LEDGER_SIGN_KEY is set; caller authorship Declared on the estates (Enforced in code when a caller keyring is set). |
| 3 | delegation-authority | Delegation | GC | 1 | Scoped, expiring, revocable delegation tokens for registered, active agents, minted and revoked ledger-first, with OAuth-style (RFC 7662-shaped) introspection, and a mint-time check of the grantor name, scope and lifetime against a roster of human grantors when FIELD_DOA_ROSTER is set (unset by default); grantor name recorded, not authenticated. |
| 4 | conformance-sentinel | Enforcement | CISO | 2 | A policy-enforcement service that, when FIELD_SENTINEL_MODE=enforce (the served default is log-only, which blocks nothing), checks each action put to it at the agent's action boundary (SDK/@governed; cooperative perimeter) against the agent's FIELD manifest and delegation token, and returns ALLOW, BLOCK or ESCALATE with a clause id; it blocks scope breaches, killed agents, and no-ledger cases before the guarded function runs, and records each verdict in the sealed ledger. + intercepted at the LLM egress when the gateway is the mandatory egress (not the default deployment). |
| 5 | kill-switch | Enforcement | CEO/CISO | 2 | Registry-flip kill of a registered, non-retired agent (one command per agent or per domain) with a measured, self-restoring drill; kill endpoints allowlisted, best-effort; only the GB10 canary manifest declares an agent-side endpoint, and the allowlist is unset by default; heartbeats for agents that check in; check-ins are not made by default. |
| 6 | spend-governor | Enforcement | CFO/CTO | 2 | On-report metering of each agent's tokens (gateway-metered when calls go through the gateway; self-reported otherwise) and cents and actions (self-reported, plus actions the sentinel meters at /check; the source label is not authenticated) against manifest caps, with integer arithmetic; it opens a human-review escalation at 80% of a cap before the cap is reached, reports BLOCK at the cap and THROTTLED (with retry_after_seconds) when a rolling per-action or token window is exhausted; the sentinel, not the governor, pauses the agent; compute has no observer (dropped, reason stated). |
| 7 | incident-replay | Ledger | CISO | 3 | A deterministic (no LLM) post-mortem that, from ledger events, the registry, delegation grants and the manifest, lists the grantor recorded on a grant covering the failing action (grantor name recorded, not authenticated), a chronological timeline of what the ledger recorded, and the first failing FIELD clause id recorded in a ledger verdict, with R/A/C/I from registry, grant, manifest with labeled defaults. |
| 8 | compliance-crosswalk | (law) | CCO/GC | 3 | Evaluates a FIELD manifest against 13 Spin State controls mapped to OSFI E-23, EU AI Act (Articles 12 and 14) and NIST AI RMF (16 of 52 entries cited, the rest pending-text), with ISO/IEC 42001 (pending text purchase) mapped but never cited; produces a named-signer evidence pack on demand (no pack without a signer; blocked by a stale-source flag until a named human clears it); Continuous (content-change detection; semantics by named review; live fetch verified manually, not in CI). |
| 9 | force-gateway | FORCE | CTO/CDO | 3 | A Messages-API proxy that injects FORCE protocol blocks into the calls sent through it and exposes regex-heuristic hygiene telemetry rates plus per-dimension drift alerts as JSON (hygiene telemetry rates + sycophancy drift (mechanism; judge off by default)), and, with FORCE_GATEWAY_ENFORCE=1 when the gateway is the mandatory egress, refuses calls from killed, revoked, unregistered, over-cap or throttled agents: org-wide when deployed as the LLM egress proxy (not the default deployment; platform judge traffic deliberately passthrough - excluded from hygiene telemetry). |
| 10 | federation-broker | Federation | CIO/GC | 4 | A crossing-decision service for agents crossing org boundaries: it validates a counterparty's FIELD manifest (valid, non-isolated, names us as a peer, Ed25519-signed when the contract holds their key; an inbound crossing without a contract key is blocked), checks the requested scope and data class against a GC-registered contract record, and ledgers the ALLOW or BLOCK verdict with its direction (best-effort). It does not carry the traffic or inspect payloads. |
| 11 | lifecycle-manager | Identity/Delegation | CIO/CHRO | 4 | provision → decommission, named re-attestation (name recorded, not authenticated): validate, register, cap, rate-limit and mint transitions, and revoke, kill and retire transitions, plus a sweep that reports tokens expiring within a horizon, re-attestation staleness against one configurable threshold, and agents whose registry owner is not on a supplied roster (escalate only; auto-kill only on an explicit flag). |
| 12 | attestation-reporter | all | CEO/board | 4 | A rollup of agents in production, a sourced conformance percentage, block, escalation and kill counts and expiring authorities, counted over a UTC-quarter window: quarterly (UTC-quarter window), Ed25519-signed by a named signer (CLI; served packs unsigned drafts unless F4). |

Two further directories are not governance systems and are not in the table: `ops-console`
(the human dashboard over the fleet) and `claude-approver` (pilot S2: answers a Claude Managed
Agents `always_ask` tool call with the sentinel's verdict; flags OFF).

Phase 0 is `packages/field-core` — models, validation, hash-chain primitives.
The client edge is `packages/field-agent` — the SDK a real agent uses to put
itself under governance in a few lines (a client, not an authority; see
`docs/INTEGRATION.md`).

## Development

Python ≥3.11 (developed on 3.14; CI runs 3.11–3.14). Keep the virtual environment outside any
cloud-synced folder to avoid sync churn.

```
pip install -e packages/field-core[dev]
pytest packages/field-core
```

Each service has its own suite and is run from its own directory. Most services import other packages
(`agent-registry`, `delegation-authority`, `lifecycle-manager`, `force-gateway` and most of the others reach
into sibling services; only `sealed-ledger`, `spend-governor`, `compliance-crosswalk` and
`defence-shield/agent-incident-retro` stand alone), so `field-core` plus the service's own `src` is not
enough. Do what CI does and install every package editable without dependencies, once:

```
pip install -e "packages/field-core[dev]"
for s in sealed-ledger agent-registry delegation-authority spend-governor kill-switch conformance-sentinel \
         incident-replay compliance-crosswalk force-gateway federation-broker lifecycle-manager \
         attestation-reporter ops-console claude-approver; do
  pip install --no-deps -e "services/$s"
done
pip install --no-deps -e packages/field-agent -e defence-shield/agent-incident-retro
pip install fastapi uvicorn httpx pytest
(cd services/<system> && python -m pytest -q tests)
```

Without installing, put every package's `src` on a **relative** `PYTHONPATH` (`;` separates entries on
Windows, `:` elsewhere). From a service directory, in bash:

```
cd services/<system>
PYTHONPATH="$(ls -d ../../packages/*/src ../../services/*/src | paste -sd: -)" python -m pytest -q tests
```

(use `paste -sd';' -` on Windows; `packages/field-agent` and `defence-shield/agent-incident-retro` sit at
the same depth and take the same `../..` prefix). Collection was checked for every service directory,
`packages/field-agent` and `defence-shield/agent-incident-retro` this way on a Python with none of the
packages installed. Run in full, every suite passes with this recipe except three tests that start
`python -m <package>` as a subprocess in another directory, where a relative path no longer resolves:
`defence-shield/agent-incident-retro` `tests/test_cli.py::test_scan_is_deterministic_across_processes`,
`packages/field-agent` `tests/test_canary_agent.py::test_the_process_never_exits_on_a_halt`, and
`services/sealed-ledger` `tests/test_operator_observer_c6_serve.py`. For those three suites use the install
procedure above, or an **absolute** path list, from the suite's own directory. On Linux and macOS:

```
R="$(git rev-parse --show-toplevel)"
PYTHONPATH="$(ls -d "$R"/packages/*/src "$R"/services/*/src | paste -sd: -)" python -m pytest -q tests
```

In Git Bash on Windows, convert the root to a drive-letter path first (`cygpath -m`) and join with `;`:

```
R="$(cygpath -m "$(git rev-parse --show-toplevel)")"
PYTHONPATH="$(ls -d "$R"/packages/*/src "$R"/services/*/src | paste -sd';' -)" python -m pytest -q tests
```

The three tests pass with the Git Bash form (a root containing spaces included). `cygpath -m` produces the
drive-letter path Windows Python understands, which the plain `$(pwd)` form warned about below does not.

A path list built from `$(pwd)` is not converted by Git Bash on Windows, and Python can then silently import
another checkout's copy of a module. When a test touches a symbol you just added, check that `hasattr`
finds it.

The CI-equivalent set is the suites above (the field-core, sealed-ledger, delegation-authority,
spend-governor, kill-switch and federation-broker run from the repository root; the others from their own
directory; `tools/tests`; `packages/field-agent/tests`; `defence-shield/agent-incident-retro/tests`) plus the
vendored-template sync check (`bash plugins/field-agent/verify_sync.sh`), the deployed-topology lint
(`python tools/topology_lint.py`) and the docker compose smoke jobs. `.github/workflows/ci.yml` is the
authoritative list.

Each system meets the same Definition of Done: `SPEC.md`, Pydantic-typed API,
CLI verbs, pytest suite with at least one adversarial case, `demo.sh` (<60s),
README with Enforced-vs-Declared table and LIMITS section.

## Naming

"Force Field Protocol" is the umbrella. "The F.O.R.C.E. Framework" and
"The F.I.E.L.D. Framework" name the acronym structures. It is never
"Force Field Framework."
