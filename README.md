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

The one-liner column is the public wording. Every word in it is backed by a cited test, or is labeled Declared, in [docs/capstone-evidence/v2-one-liners.md](docs/capstone-evidence/v2-one-liners.md); `python tools/e_gate.py` checks that. Estate status is Declared for every row until the estates run these images and the Phase G arming is live. Nothing here is a compliance or certification claim.

| # | System | FIELD letter | Exec owner | Phase | One-liner |
|---|--------|--------------|-----------|-------|---|
| 1 | agent-registry | Identity | CIO | 1 | System of record for each registered agent's identity, human owner and manifest reference; surfaces unregistered workflows and accounts from the artifacts you feed it and from API-key scans (file-based, heuristic). |
| 2 | sealed-ledger | Ledger | CFO/audit | 1 | Hash-chained, Ed25519-anchored append-only record with offline-verifiable export; estate-level retention by segment rotation (mechanism; no estate rotates today, key custody undecided); per-event ledger-signed when the key is set, caller authorship Declared. |
| 3 | delegation-authority | Delegation | GC | 1 | OAuth-style scoped, expiring, revocable tokens bound to a registered active agent; mint checked against a DOA roster when FIELD_DOA_ROSTER is set; grantor name recorded, not authenticated. |
| 4 | conformance-sentinel | Enforcement | CISO | 2 | Checks each action an agent asks about against its manifest, token and the registry and blocks breaches before they run, at the agent's action boundary (SDK/@governed; cooperative perimeter), + intercepted at the LLM egress when the gateway is the mandatory egress (not deployed as such on either estate). |
| 5 | kill-switch | Enforcement | CEO/CISO | 2 | One-command kill, domain kill and drill mode; kill endpoints allowlisted, best-effort (one shipped manifest declares an agent-side endpoint); heartbeats for agents that check in (none do on either estate today). |
| 6 | spend-governor | Enforcement | CFO/CTO | 2 | Platform-metered actions and tokens against manifest caps; throttle (per-action windows over action counts; `session` Declared); escalates to a human before the cap; compute has no observer (dropped, reason stated). |
| 7 | incident-replay | Ledger | CISO | 3 | Reconstructs who authorized an agent, what it did and which clause failed from ledger, registry, delegation and manifest after verifying the chain; RACI R/A/C/I from registry, grant and manifest with labeled defaults. |
| 8 | compliance-crosswalk | (law) | CCO/GC | 3 | Maps platform controls to cited clauses of OSFI E-23, EU AI Act, ISO/IEC 42001 (pending text purchase) and NIST AI RMF; evidence pack on demand with a named signer; Continuous (content-change detection; semantics by named review; live fetch verified manually, not in CI). |
| 9 | force-gateway | FORCE | CTO/CDO | 3 | LLM-traffic proxy that injects the FORCE block and records hygiene telemetry (counters, not content); org-wide when deployed as the LLM egress proxy (not deployed as such on either estate); sycophancy drift (mechanism; judge off on both estates today). |
| 10 | federation-broker | Federation | CIO/GC | 4 | Crossing-decision service: validates counterparty manifests and checks contract scope and data-class allowlists on the request envelope; inbound needs a keyed, signed contract; it decides and does not carry the traffic. |
| 11 | lifecycle-manager | Identity/Delegation | CIO/CHRO | 4 | Provision to decommission with named re-attestation (name recorded, not authenticated); expiry and orphan sweep against an owner roster file (unset on both estates). |
| 12 | attestation-reporter | all | CEO/board | 4 | Quarterly (UTC-quarter window), Ed25519-signed by a named signer (CLI; served packs are unsigned drafts unless the signer and key are set). |

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
