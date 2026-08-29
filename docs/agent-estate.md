# Agent Estate — governance metrics

Document-ready figures for the FIELD Platform agent estate. Two columns:

- **PoC platform** — **real** telemetry captured from a freshly-booted FIELD
  stack running the synthetic 3-agent demo fleet. Snapshot 2026-08-11. These
  are genuine service outputs, **clearly synthetic** (demo agents, demo
  owners), not a production estate.
- **Production estate** — **Deferred to Sentinel PoC telemetry (Claude Code
  build).** The FIELD services are not long-running daemons; there is no
  standing production fleet in this repo. Real estate numbers come from the
  Sentinel proof-of-concept instrumenting live Claude Code agents, and are
  filled in from that telemetry when available.

> **Honesty line (unchanged product rule):** no number without a source, and
> no number invented. Every PoC figure below prints the live query it came
> from. Every production figure is an explicit deferral, never a placeholder
> guess.

## Estate summary

| Metric | PoC platform (synthetic demo, 2026-08-11) | Production estate | Source query |
|---|---|---|---|
| Agents registered | **3** | Deferred → Sentinel PoC | `GET :8001/agents` |
| Agents in production (active) | **3** | Deferred → Sentinel PoC | `GET :8001/agents?status=active` |
| Agents killed | **0** | Deferred → Sentinel PoC | `GET :8001/agents?status=killed` |
| Distinct human owners | **3** (RevOps Lead, FP&A Lead, AP Team Lead) | Deferred → Sentinel PoC | `GET :8001/agents` |
| Domains covered | **2** (finance ×2, sales ×1) | Deferred → Sentinel PoC | `GET :8001/agents` |
| Delegation tokens — active | **3** | Deferred → Sentinel PoC | `GET :8003/tokens` |
| Delegation tokens — expiring ≤30 d / revoked | **0 / 0** | Deferred → Sentinel PoC | `GET :8003/tokens` |
| Conformance rate (ALLOW ÷ all verdicts) | **75.0 %** (3 ALLOW, 1 BLOCK, 0 ESCALATE) | Deferred → Sentinel PoC | `GET :8002/events?event_type=conformance.*` |
| Spend escalations open (human queue) | **1** (invoicing-agent, 82 % of cap) | Deferred → Sentinel PoC | `GET :8006/escalations` |
| Ledger chain integrity | **INTACT** (13 events) | Deferred → Sentinel PoC | `GET :8002/verify` |

## Token usage & cost (the new governance signal)

Agents self-report token usage; FIELD prices it from a dated, sourced price
book and flags rogue usage. PoC figures are live from the demo stack.

| Agent (owner · domain) | Model reported | In / Out tokens | Cost | Model on allow-list? | Rogue flags |
|---|---|---|---|---|---|
| crm-enrich-agent (RevOps Lead · sales) | claude-haiku-4-5 | 80,000 / 12,000 | **$0.14** | ✅ yes | 0 |
| forecast-agent (FP&A Lead · finance) | claude-sonnet-5 | 120,000 / 30,000 | **$0.54** | ✅ yes | 0 |
| invoicing-agent (AP Team Lead · finance) | **claude-opus-4-8** | 60,000 / 15,000 | **$0.67** | ❌ **no** (Haiku-only) | **1 — off-list model** |
| **Estate total** | — | **260,000 / 57,000** (317,000) | **$1.36** | — | **1** |

Source: `GET :8006/usage/{agent_id}` per registered agent · `GET :8002/events?event_type=usage.*`

**Rogue signal in this snapshot:** invoicing-agent is authorised for
`claude-haiku-4-5` only but reported `claude-opus-4-8` usage — a
`usage.rogue_model` event on the ledger and one open human flag. Cost
illustrates *why* it matters: the same 75,000 tokens cost **$0.675 on Opus**
versus **$0.135 on Haiku** (its allow-listed model) — exactly **5×
overspend** from an off-list model (Opus lists at 5× Haiku on both input and
output). This is exactly the "monitor token usage / identify rogue token
usage" goal, made a ledgered, priced, escalated fact.

## Cost provenance (so no dollar figure is unsourced)

Price book `anthropic-list-2026-08-10`. Source: *Anthropic public list
price, first-party Claude API,
platform.claude.com/docs/en/about-claude/pricing (retrieved 2026-08-10)*.
Rates are the official list, not invented; integer arithmetic (1e-7 USD
units), never floats near a cap.

| Model | Input $/MTok | Output $/MTok |
|---|---|---|
| claude-haiku-4-5 | $1 | $5 |
| claude-sonnet-5 | $2 | $10 |
| claude-opus-4-8 | $5 | $25 |

Worked example (invoicing-agent, Opus): 60,000 × $5/MTok + 15,000 ×
$25/MTok = $0.30 + $0.375 = **$0.675 → $0.67**.

## How the production numbers arrive

The Sentinel PoC (Claude Code build) instruments live Claude Code agents
through the FIELD spine: each agent reports token usage to spend-governor
`/usage` (or via force-gateway auto-metering), the governor prices and
rogue-checks it, and every figure in the tables above becomes a live query
against that running estate — the same endpoints, populated with real
fleet data. Until then, the Production column stays a labelled deferral.

---
*Generated 2026-08-11 from a live FIELD stack (synthetic demo fleet). Regenerate:
`bash services/ops-console/demo.sh` then `GET http://127.0.0.1:8011/api/overview`.*
