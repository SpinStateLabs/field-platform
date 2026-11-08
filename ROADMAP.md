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
| Conformance Sentinel | E · CISO | shipped (`services/conformance-sentinel`) | built (log-only ✓ · scorecard · semantic judge · self-manifest: `mode.py`, `measure.py`, `judge.py`, `self_manifest.py`) | A policy-enforcement service that, when FIELD_SENTINEL_MODE=enforce (the served default is log-only, which blocks nothing), checks each action put to it at the agent's action boundary (SDK/@governed; cooperative perimeter) against the agent's FIELD manifest and delegation token, and returns ALLOW, BLOCK or ESCALATE with a clause id; it blocks scope breaches, killed agents, and no-ledger cases before the guarded function runs, and records each verdict in the sealed ledger. + intercepted at the LLM egress when the gateway is the mandatory egress (not the default deployment). |
| FORCE Gateway | FORCE · CTO/CDO | shipped (`services/force-gateway`) | built (sampled hygiene judge · trend alerts · telemetry: `hygiene_judge.py`, `drift.py`, `telemetry.py`; the instrumentation is fail-open and capped; enforce mode `FORCE_GATEWAY_ENFORCE=1` is a separate opt-in, see its README) | A Messages-API proxy that injects FORCE protocol blocks into the calls sent through it and exposes regex-heuristic hygiene telemetry rates plus per-dimension drift alerts as JSON (hygiene telemetry rates + sycophancy drift (mechanism; judge off by default)), and, with FORCE_GATEWAY_ENFORCE=1 when the gateway is the mandatory egress, refuses calls from killed, revoked, unregistered, over-cap or throttled agents: org-wide when deployed as the LLM egress proxy (not the default deployment; platform judge traffic deliberately passthrough - excluded from hygiene telemetry). |
| Compliance Crosswalk | law · CCO/GC | shipped (`services/compliance-crosswalk`) | built (gated suggestions · evidence-pack generator · reg-version staleness · regwatch: `suggestions.py`, `evidence_pack.py`, `staleness.py`, `regwatch.py`) | Evaluates a FIELD manifest against 13 Spin State controls mapped to OSFI E-23, EU AI Act (Articles 12 and 14) and NIST AI RMF (16 of 52 entries cited, the rest pending-text), with ISO/IEC 42001 (pending text purchase) mapped but never cited; produces a named-signer evidence pack on demand (no pack without a signer; blocked by a stale-source flag until a named human clears it); Continuous (content-change detection; semantics by named review; live fetch verified manually, not in CI). |

## The nine platform systems — SHIPPED

The original brief lists these as *future* roadmap items. In this repo they are
**already built and tested** — the roadmap records that reality.

1. **Agent Registry** — A register of agents (one record per unique agent id, a non-empty human owner string, and a manifest reference that must resolve to a valid manifest when one is set at registration) with discovery of unregistered shadow-agent candidates from supplied artifacts: service-account CSVs, an n8n workflow export, and API-key scans (file-based, heuristic). (I · CIO) — `services/agent-registry` ✓
2. **Delegation Authority Service** — Scoped, expiring, revocable delegation tokens for registered, active agents, minted and revoked ledger-first, with OAuth-style (RFC 7662-shaped) introspection, and a mint-time check of the grantor name, scope and lifetime against a roster of human grantors when FIELD_DOA_ROSTER is set (unset by default); grantor name recorded, not authenticated. (D · GC) — `services/delegation-authority` ✓
3. **Kill-Switch Command Plane** — Registry-flip kill of a registered, non-retired agent (one command per agent or per domain) with a measured, self-restoring drill; kill endpoints allowlisted, best-effort; only the GB10 canary manifest declares an agent-side endpoint, and the allowlist is unset by default; heartbeats for agents that check in; check-ins are not made by default. (E · CEO/CISO) — `services/kill-switch` ✓
4. **Sealed Ledger Service** — A tamper-evident record of events appended by estate services: hash-chained, Ed25519-anchored; estate-level retention by segment rotation (mechanism; rotation is not armed by default - key custody undecided); an offline-re-verifiable export (a served export is unsigned); per-event ledger-signed when FIELD_LEDGER_SIGN_KEY is set; caller authorship Declared on the estates (Enforced in code when a caller keyring is set). (L · CFO/audit) — `services/sealed-ledger` ✓
5. **Incident Replay Agent** — A deterministic (no LLM) post-mortem that, from ledger events, the registry, delegation grants and the manifest, lists the grantor recorded on a grant covering the failing action (grantor name recorded, not authenticated), a chronological timeline of what the ledger recorded, and the first failing FIELD clause id recorded in a ledger verdict, with R/A/C/I from registry, grant, manifest with labeled defaults. (L · CISO) — `services/incident-replay` ✓
6. **Federation Broker** — A crossing-decision service for agents crossing org boundaries: it validates a counterparty's FIELD manifest (valid, non-isolated, names us as a peer, Ed25519-signed when the contract holds their key; an inbound crossing without a contract key is blocked), checks the requested scope and data class against a GC-registered contract record, and ledgers the ALLOW or BLOCK verdict with its direction (best-effort). It does not carry the traffic or inspect payloads. (F · CIO/GC) — `services/federation-broker` ✓
7. **Spend & Resource Governor** — On-report metering of each agent's tokens (gateway-metered when calls go through the gateway; self-reported otherwise) and cents and actions (self-reported, plus actions the sentinel meters at /check; the source label is not authenticated) against manifest caps, with integer arithmetic; it opens a human-review escalation at 80% of a cap before the cap is reached, reports BLOCK at the cap and THROTTLED (with retry_after_seconds) when a rolling per-action or token window is exhausted; the sentinel, not the governor, pauses the agent; compute has no observer (dropped, reason stated). (E · CFO/CTO) — `services/spend-governor` ✓
8. **Agent Lifecycle Manager** — provision → decommission, named re-attestation (name recorded, not authenticated): validate, register, cap, rate-limit and mint transitions, and revoke, kill and retire transitions, plus a sweep that reports tokens expiring within a horizon, re-attestation staleness against one configurable threshold, and agents whose registry owner is not on a supplied roster (escalate only; auto-kill only on an explicit flag). (I/D · CIO/CHRO) — `services/lifecycle-manager` ✓
9. **Executive Attestation Reporter** — A rollup of agents in production, a sourced conformance percentage, block, escalation and kill counts and expiring authorities, counted over a UTC-quarter window: quarterly (UTC-quarter window), Ed25519-signed by a named signer (CLI; served packs unsigned drafts unless F4). (all · CEO/board) — `services/attestation-reporter` ✓

Plus **ops-console** (`services/ops-console`) — the human dashboard over the fleet — and
**claude-approver** (`services/claude-approver`, pilot S2, flags OFF): 14 service directories in all.

## Notes

- All figures traceable to live queries or tests; CI runs py 3.11–3.14 + x86_64 compose; arm64 is a supported target. Test count: 12,642 tests
  collected at 2bc5643e7 on 2026-11-07 (`python -m pytest --collect-only -q`, run once on Python 3.14.5 from
  each suite's own directory and summed over 17 suites: the 14 services with a test directory 5,971, the 2
  packages 2,226, `tools/tests` 4,445; `services/field-mcp` has no test directory and collects none;
  collected, not passed, and not the CI matrix total). It was 10,390 at cd3b769 on 2026-11-04 and 8,308 at
  a9dc4f3 on 2026-10-30. What merged in between is listed at the top of `STATE.md` (MERGE 1 to MERGE 20).
- **field-agent client SDK** (`packages/field-agent`, 2026-08-29) — the last
  mile: governed actions, strict usage metering, fail-closed heartbeat in a
  few lines; `docs/INTEGRATION.md`.
- The `SpinStateLabs/Force-Field` marketplace ROADMAP can be synced separately if
  these are packaged there as plugins.
