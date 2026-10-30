# ROADMAP — FIELD Platform

This repo is the reference implementation of the Force Field Protocol. Honesty
line: this file records **what is built**, not a wishlist. Status is verifiable
against `services/` and CI.

## v0 trio — the public "enforcement in v1.1" commitment

Deterministic cores **shipped**; the ADR delta (semantic LLM layers, log-only
mode, measurement harnesses — see `docs/adr/`) is **built** for all three (code on main; see
`STATE.md` for history).

| System | FIELD letter · buyer | Deterministic core | ADR delta | One-liner |
|---|---|---|---|---|
| Conformance Sentinel | E · CISO | shipped (`services/conformance-sentinel`) | built (log-only ✓ · scorecard · semantic judge · self-manifest: `mode.py`, `measure.py`, `judge.py`, `self_manifest.py`) | Checks each action an agent asks about against its manifest, token and the registry and blocks breaches before they run, at the agent's action boundary (SDK/@governed; cooperative perimeter), + intercepted at the LLM egress when the gateway is the mandatory egress (not deployed as such on either estate). |
| FORCE Gateway | FORCE · CTO/CDO | shipped (`services/force-gateway`) | built (sampled hygiene judge · trend alerts · telemetry: `hygiene_judge.py`, `drift.py`, `telemetry.py`; the instrumentation is fail-open and capped; enforce mode `FORCE_GATEWAY_ENFORCE=1` is a separate opt-in, see its README) | LLM-traffic proxy that injects the FORCE block and records hygiene telemetry (counters, not content); org-wide when deployed as the LLM egress proxy (not deployed as such on either estate); sycophancy drift (mechanism; judge off on both estates today). |
| Compliance Crosswalk | law · CCO/GC | shipped (`services/compliance-crosswalk`) | built (gated suggestions · evidence-pack generator · reg-version staleness · regwatch: `suggestions.py`, `evidence_pack.py`, `staleness.py`, `regwatch.py`) | Maps platform controls to cited clauses of OSFI E-23, EU AI Act, ISO/IEC 42001 (pending text purchase) and NIST AI RMF; evidence pack on demand with a named signer; Continuous (content-change detection; semantics by named review; live fetch verified manually, not in CI). |

## The nine platform systems — BUILT

The original brief lists these as *future* roadmap items. In this repo they are
**built and tested**; the wording below is the Phase E wording, and every word in it is either
backed by a cited test or labeled Declared in `docs/capstone-evidence/v2-one-liners.md`
(`python tools/e_gate.py` checks it). Estate status is Declared for every system until the
estates run these images and the Phase G arming is live.

1. **Agent Registry** — System of record for each registered agent's identity, human owner and manifest reference; surfaces unregistered workflows and accounts from the artifacts you feed it and from API-key scans (file-based, heuristic). — `services/agent-registry` ✓
2. **Delegation Authority Service** — OAuth-style scoped, expiring, revocable tokens bound to a registered active agent; mint checked against a DOA roster when FIELD_DOA_ROSTER is set; grantor name recorded, not authenticated. — `services/delegation-authority` ✓
3. **Kill-Switch Command Plane** — One-command kill, domain kill and drill mode; kill endpoints allowlisted, best-effort (one shipped manifest declares an agent-side endpoint); heartbeats for agents that check in (none do on either estate today). — `services/kill-switch` ✓
4. **Sealed Ledger Service** — Hash-chained, Ed25519-anchored append-only record with offline-verifiable export; estate-level retention by segment rotation (mechanism; no estate rotates today, key custody undecided); per-event ledger-signed when the key is set, caller authorship Declared. — `services/sealed-ledger` ✓
5. **Incident Replay Agent** — Reconstructs who authorized an agent, what it did and which clause failed from ledger, registry, delegation and manifest after verifying the chain; RACI R/A/C/I from registry, grant and manifest with labeled defaults. — `services/incident-replay` ✓
6. **Federation Broker** — Crossing-decision service: validates counterparty manifests and checks contract scope and data-class allowlists on the request envelope; inbound needs a keyed, signed contract; it decides and does not carry the traffic. — `services/federation-broker` ✓
7. **Spend & Resource Governor** — Platform-metered actions and tokens against manifest caps; throttle (per-action windows over action counts; `session` Declared); escalates to a human before the cap; compute has no observer (dropped, reason stated). — `services/spend-governor` ✓
8. **Agent Lifecycle Manager** — Provision to decommission with named re-attestation (name recorded, not authenticated); expiry and orphan sweep against an owner roster file (unset on both estates). — `services/lifecycle-manager` ✓
9. **Executive Attestation Reporter** — Quarterly (UTC-quarter window), Ed25519-signed by a named signer (CLI; served packs are unsigned drafts unless the signer and key are set). — `services/attestation-reporter` ✓

Plus **ops-console** (`services/ops-console`) — the human dashboard over the fleet — and
**claude-approver** (`services/claude-approver`, pilot S2, flags OFF): 14 service directories in all.

## Notes

- All figures traceable to live queries or tests; CI runs py 3.11–3.14 + x86_64 compose; arm64 is a supported target. Test count: 8,172
  tests collected (collected, not passed) at 48acfa6 on 2026-10-30, from `python -m pytest --collect-only -q`
  run per package as CI runs them: field-core + sealed-ledger + delegation-authority + spend-governor +
  kill-switch + federation-broker 2,574 (one process); agent-registry 304; conformance-sentinel 256;
  incident-replay 91; compliance-crosswalk 358; force-gateway 443; lifecycle-manager 224;
  attestation-reporter 135; ops-console 236; claude-approver 279; field-agent 151;
  defence-shield/agent-incident-retro 229; tools/tests 2,892.
- **field-agent client SDK** (`packages/field-agent`, 2026-08-29) — the last
  mile: governed actions, strict usage metering, fail-closed heartbeat in a
  few lines; `docs/INTEGRATION.md`.
- The `SpinStateLabs/Force-Field` marketplace ROADMAP can be synced separately if
  these are packaged there as plugins.
