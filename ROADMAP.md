# ROADMAP — FIELD Platform

This repo is the reference implementation of the Force Field Protocol. Honesty
line: this file records **what is built**, not a wishlist. Status is verifiable
against `services/` and CI.

## v0 trio — the public "enforcement in v1.1" commitment

Deterministic cores **shipped**; the ADR delta (semantic LLM layers, log-only
mode, measurement harnesses — see `docs/adr/`) is **built** for all three (code on main; see
`STATE.md` for history).

| System | FIELD letter · buyer | Deterministic core | ADR delta |
|---|---|---|---|
| Conformance Sentinel | E · CISO | shipped (`services/conformance-sentinel`) | built (log-only ✓ · scorecard · semantic judge · self-manifest: `mode.py`, `measure.py`, `judge.py`, `self_manifest.py`) |
| FORCE Gateway | FORCE · CTO/CDO | shipped (`services/force-gateway`) | built (sampled hygiene judge · trend alerts · telemetry: `hygiene_judge.py`, `drift.py`, `telemetry.py`; the instrumentation is fail-open and capped; enforce mode `FORCE_GATEWAY_ENFORCE=1` is a separate opt-in, see its README) |
| Compliance Crosswalk | law · CCO/GC | shipped (`services/compliance-crosswalk`) | built (gated suggestions · evidence-pack generator · reg-version staleness · regwatch: `suggestions.py`, `evidence_pack.py`, `staleness.py`, `regwatch.py`) |

## The nine platform systems — SHIPPED

The original brief lists these as *future* roadmap items. In this repo they are
**built and tested**. The wording below is the Phase E wording: every word is classified
Enforced or Declared, with its cited test, in `docs/capstone-evidence/v2-one-liners.md`.
Both estates run pre-v1.2 images, so per-system estate status is Declared until redeploy.

1. **Agent Registry** — Registry of AI agents: identity, owner (a recorded string, not verified as a current human) and a manifest reference that must resolve when set. Discovery turns an n8n export, a service-account inventory, a credential-inventory CSV and pasted text into a review queue. API-key scans are file-based and heuristic: no live IAM connector; coverage is only what you feed it. — `services/agent-registry`
2. **Delegation Authority Service** — Scoped, expiring, revocable delegation tokens bound to a registered, active agent; every mint and revoke is ledgered before it takes effect. Mint is checked against a DOA roster only when FIELD_DOA_ROSTER is set (estate setting not verified; see v2-one-liners.md); grantor name recorded, not authenticated. OAuth-style: RFC 7662-shaped introspection of opaque database tokens, not an OAuth server. — `services/delegation-authority`
3. **Kill-Switch Command Plane** — One command halts an agent, or every agent in a registry domain, by flipping its registry status; its heartbeat poll then says halt and the sentinel blocks its next check. Drill mode kills, verifies, restores. Kill endpoints: allowlisted, best-effort signal, not a process stop; only canary-gb10 declares one. Heartbeats for agents that check in; none do on either estate today. — `services/kill-switch`
4. **Sealed Ledger Service** — Hash-chained (sha-256) record of agent actions with Ed25519-anchored heads; per-event ledger-signed when the signing key is set (caller authorship Declared); auditor export re-verifiable offline (served export unsigned); estate retention by segment rotation (mechanism; no estate rotates today, key custody undecided). — `services/sealed-ledger`
5. **Incident Replay Agent** — Reconstructs from the sealed ledger who granted authority, what ran, and which manifest clause failed first, after verifying the chain (tampered or busy ledgers are flagged, never reported clean). RACI-seeded: R/A/C/I from registry, grant, manifest with labeled defaults; names are recorded strings, and replay is only as complete as the ledger. — `services/incident-replay`
6. **Federation Broker** — Crossing-decision service, not a traffic proxy: validates counterparty manifests, verifies their Ed25519 signature inbound against a contract-registered key (keyless contract blocks inbound), allows only the contract's scopes and data-class labels (envelope only, no payload inspection), and ledgers each verdict. Cooperative: an agent that does not ask is invisible. — `services/federation-broker`
7. **Spend & Resource Governor** — Meters agent tokens and actions against manifest caps in integer cents; escalates to a human queue at 80% before the cap; reports BLOCK at the cap and THROTTLED over rolling per-action windows (periods the governor can parse; session Declared). Actions metered at the sentinel, tokens at the gateway; otherwise self-reported; compute has no observer (dropped). — `services/spend-governor`
8. **Agent Lifecycle Manager** — Detects expiring authorities, stale re-attestation (attester name recorded, not authenticated) and orphaned agents against an owners roster; auto-kill only with an explicit flag. CLI provision (validate, register, cap, mint) and decommission (revoke, kill, retire). Sweep not scheduled on either estate (roster unset). — `services/lifecycle-manager`
9. **Executive Attestation Reporter** — Board pack of estate counts, shadow-aware conformance % (formula printed) and incident counts; no number without its source query, unavailable never zero, tampered chain shown BROKEN. Windowed to a UTC quarter; Ed25519-signed by a named signer via CLI; served packs are unsigned drafts unless the estate key is set. Key custody Declared. — `services/attestation-reporter`

Plus **ops-console** (`services/ops-console`) — the human dashboard over the fleet — and
**claude-approver** (`services/claude-approver`, pilot S2, flags OFF): 14 service directories in all.

## Notes

- All figures traceable to live queries or tests; CI runs py 3.11–3.14 + x86_64 compose; arm64 is a supported target. Test count: 8,172 tests **collected** (not passed) across 18 packages at main 48acfa6 on 2026-10-30, by
  `python -m pytest --collect-only -q tests` in each package directory as CI does (field-core 1,120; field-agent 151;
  defence-shield 229; tools 2,892; agent-registry 304; attestation-reporter 135; claude-approver 279;
  compliance-crosswalk 358; conformance-sentinel 256; delegation-authority 213; federation-broker 95;
  force-gateway 443; incident-replay 91; kill-switch 160; lifecycle-manager 224; ops-console 236;
  sealed-ledger 744; spend-governor 242). A collected count says nothing about pass or fail; the earlier
  figure of about 6,400 passed was one GX10 run of 13 suites on the same day.
- **field-agent client SDK** (`packages/field-agent`, 2026-08-29) — the last
  mile: governed actions, strict usage metering, fail-closed heartbeat in a
  few lines; `docs/INTEGRATION.md`.
- The `SpinStateLabs/Force-Field` marketplace ROADMAP can be synced separately if
  these are packaged there as plugins.
