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

| # | System | One-liner (Enforced vs Declared: `docs/capstone-evidence/v2-one-liners.md`) | FIELD letter | Exec owner | Phase |
|---|--------|---|--------------|-----------|-------|
| 1 | agent-registry | Registry of AI agents: identity, owner (a recorded string, not verified as a current human) and a manifest reference that must resolve when set. Discovery turns an n8n export, a service-account inventory, a credential-inventory CSV and pasted text into a review queue. API-key scans are file-based and heuristic: no live IAM connector; coverage is only what you feed it. | Identity | CIO | 1 |
| 2 | sealed-ledger | Hash-chained (sha-256) record of agent actions with Ed25519-anchored heads; per-event ledger-signed when the signing key is set (caller authorship Declared); auditor export re-verifiable offline (served export unsigned); estate retention by segment rotation (mechanism; no estate rotates today, key custody undecided). | Ledger | CFO/audit | 1 |
| 3 | delegation-authority | Scoped, expiring, revocable delegation tokens bound to a registered, active agent; every mint and revoke is ledgered before it takes effect. Mint is checked against a DOA roster only when FIELD_DOA_ROSTER is set (estate setting not verified; see v2-one-liners.md); grantor name recorded, not authenticated. OAuth-style: RFC 7662-shaped introspection of opaque database tokens, not an OAuth server. | Delegation | GC | 1 |
| 4 | conformance-sentinel | Checks each proposed action against the agent's manifest, token, kill status, ledger and rate window at the agent's action boundary (SDK/@governed; cooperative perimeter: a process that does not ask is not stopped). In enforce mode it blocks before execution. Also intercepted at the LLM egress when the gateway is the mandatory egress (not deployed as such on either estate). | Enforcement | CISO | 2 |
| 5 | kill-switch | One command halts an agent, or every agent in a registry domain, by flipping its registry status; its heartbeat poll then says halt and the sentinel blocks its next check. Drill mode kills, verifies, restores. Kill endpoints: allowlisted, best-effort signal, not a process stop; only canary-gb10 declares one. Heartbeats for agents that check in; none do on either estate today. | Enforcement | CEO/CISO | 2 |
| 6 | spend-governor | Meters agent tokens and actions against manifest caps in integer cents; escalates to a human queue at 80% before the cap; reports BLOCK at the cap and THROTTLED over rolling per-action windows (periods the governor can parse; session Declared). Actions metered at the sentinel, tokens at the gateway; otherwise self-reported; compute has no observer (dropped). | Enforcement | CFO/CTO | 2 |
| 7 | incident-replay | Reconstructs from the sealed ledger who granted authority, what ran, and which manifest clause failed first, after verifying the chain (tampered or busy ledgers are flagged, never reported clean). RACI-seeded: R/A/C/I from registry, grant, manifest with labeled defaults; names are recorded strings, and replay is only as complete as the ledger. | Ledger | CISO | 3 |
| 8 | compliance-crosswalk | Maps FIELD manifest fields to OSFI E-23, EU AI Act and NIST AI RMF controls, citing only retrieved text (ISO/IEC 42001 pending text purchase, none cited). On-demand evidence pack: named signer required, unsigned, blocked while a source-change flag stands. Scheduled content-change detection of cited sources (semantics by named review; live fetch verified manually, not in CI). | (law) | CCO/GC | 3 |
| 9 | force-gateway | Reverse proxy that injects the FORCE runtime protocol into model calls routed through it, preserving the caller's system prompt, and records regex hygiene telemetry (mechanism; judge and sycophancy drift off on both estates). Fails open. With ENFORCE=1 and the gateway as mandatory egress (not deployed so on either estate) it also intercepts calls. Not org-wide. | FORCE | CTO/CDO | 3 |
| 10 | federation-broker | Crossing-decision service, not a traffic proxy: validates counterparty manifests, verifies their Ed25519 signature inbound against a contract-registered key (keyless contract blocks inbound), allows only the contract's scopes and data-class labels (envelope only, no payload inspection), and ledgers each verdict. Cooperative: an agent that does not ask is invisible. | Federation | CIO/GC | 4 |
| 11 | lifecycle-manager | Detects expiring authorities, stale re-attestation (attester name recorded, not authenticated) and orphaned agents against an owners roster; auto-kill only with an explicit flag. CLI provision (validate, register, cap, mint) and decommission (revoke, kill, retire). Sweep not scheduled on either estate (roster unset). | Identity/Delegation | CIO/CHRO | 4 |
| 12 | attestation-reporter | Board pack of estate counts, shadow-aware conformance % (formula printed) and incident counts; no number without its source query, unavailable never zero, tampered chain shown BROKEN. Windowed to a UTC quarter; Ed25519-signed by a named signer via CLI; served packs are unsigned drafts unless the estate key is set. Key custody Declared. | all | CEO/board | 4 |

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
