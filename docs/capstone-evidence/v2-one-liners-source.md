# v2 one-liners — the source text (provenance record)

**What this is.** The verbatim product one-liners the 2026-09-12 audit checked the
build against, recovered 2026-09-12 from
`AI-CTO/claude-files/Force-Field_Build_Prompt.md` (outside this repo, Don's
capstone working folder). Plan item E1 required an authoritative "old" column;
this file is it. Nothing here is a claim about the build — every one of these
sentences is what the audit found overclaiming. The rewritten wording lives in
`v2-one-liners.md` (written in Phase E); the audit's per-row reasons are in
`../../../tasks/audit-v2-12-systems-vs-production-build-2026-09-12.md`.

**Numbering.** The audit numbers 1–12. The source document numbers them in two
groups: the "v0 trio" (Systems 1–3 of the build prompt = Conformance Sentinel,
FORCE Gateway, Compliance Crosswalk) and the "nine platform systems" (numbered
1–9 in the prompt's ROADMAP section). The mapping is given per row.

| # (audit) | System | Source location |
|---|---|---|
| 1 | Agent Registry | ROADMAP list item 1 |
| 2 | Conformance Sentinel | "System 1 — Conformance Sentinel (FIELD-E) — the v1.1 commitment" |
| 3 | Delegation Authority Service | ROADMAP list item 2 |
| 4 | Kill-Switch Command Plane | ROADMAP list item 3 |
| 5 | Sealed Ledger Service | ROADMAP list item 4 |
| 6 | Incident Replay Agent | ROADMAP list item 5 |
| 7 | Compliance Crosswalk Engine | "System 3 — Compliance Crosswalk Engine" |
| 8 | Federation Broker | ROADMAP list item 6 |
| 9 | Spend & Resource Governor | ROADMAP list item 7 |
| 10 | FORCE Gateway | "System 2 — FORCE Gateway" |
| 11 | Agent Lifecycle Manager | ROADMAP list item 8 |
| 12 | Executive Attestation Reporter | ROADMAP list item 9 |

---

## The twelve, verbatim

**1 — Agent Registry** ("the passport office") — system of record where every AI
agent is registered with identity, owner, and FIELD manifest; discovers
unregistered shadow agents by scanning service accounts, API keys, and workflow
platforms. (FIELD-I · CIO)

**2 — Conformance Sentinel** — An agent that continuously audits deployed agents
against their FIELD manifests and blocks non-conforming actions at the
policy-enforcement point — scope breaches, expired authority, missing ledger
writes — before they execute.

**3 — Delegation Authority Service** — scoped, expiring, revocable authority
tokens chained to the human delegation-of-authority matrix; every agent action
traces to a named human grant. OAuth for agents. (FIELD-D · GC)

**4 — Kill-Switch Command Plane** — resolvable kill endpoints and heartbeats for
every registered agent; one-command domain shutdown and drill mode.
(FIELD-E · CEO/CISO)

**5 — Sealed Ledger Service** — managed, cryptographically chained append-only
record of agent actions with auditor read-only export and retention policies.
(FIELD-L · CFO/audit committee)

**6 — Incident Replay Agent** — reconstructs from the ledger who authorized an
agent, what it did, and which manifest clause failed; outputs the RACI-ready
post-mortem. (FIELD-L · CISO)

**7 — Compliance Crosswalk Engine** — Maps every FIELD manifest to OSFI E-23, EU
AI Act, ISO 42001, and NIST AI RMF control requirements, and generates the
evidence pack on demand.

**8 — Federation Broker** — trust gateway for agents crossing org boundaries;
validates counterparty manifests, enforces data-scope borders, records inter-org
contract semantics. (FIELD-F · CIO/GC)

**9 — Spend & Resource Governor** — real-time metering of every agent's token,
compute, and action spend against manifest caps; throttles at thresholds,
escalates to a human before the budget event. (FIELD-E · CFO/CTO)

**10 — FORCE Gateway** — An LLM-traffic proxy that injects FORCE runtime
constraints on outbound model calls and dashboards hygiene telemetry. Governs
what the AI says while FIELD governs what it is.

**11 — Agent Lifecycle Manager** — provisioning-to-decommission: authority
expiry, re-attestation cadences, orphan detection for agents whose human owner
left. (FIELD-I/D · CIO/CHRO)

**12 — Executive Attestation Reporter** — board-level rollup: agents in
production, conformance percentage, incidents and replays, expiring authorities;
generates the quarterly AI-governance attestation the CEO signs.
(all letters · CEO/board)

---

## Notes for Phase E

- The audit's "Words in the v2 one-liners with no implementation behind them"
  table quotes fragments of these sentences; this file is where the fragments
  come from. Where the audit quotes a phrase that is not literally present (for
  example "API-key scans" for row 1, "Continuous" for row 7, "org-wide" for row
  10), the audit is paraphrasing the underlying claim — E1 must quote THIS text
  as the old column and note the paraphrase.
- Four audience decks consume the audit's findings:
  `presentations/src/deck-c.js` (capstone, slide 16 = the rewording table) and
  `deck-a.js` (board briefing) name specific phrases. When E1 settles the new
  wording, those decks must be regenerated (`node deck-c.js`) or they will drift
  from the repo. `presentations/README.md` records that Don's per-row sign-off
  on the rewording table was still open.
