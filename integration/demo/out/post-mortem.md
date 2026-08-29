# Post-mortem — invoicing-agent

*Window:* `2020-01-01T00:00:00+00:00` → `2030-01-01T00:00:00+00:00` · *Generated:* 2026-08-29T14:07:42.141047+00:00
*Ledger integrity:* OK — chain intact over 23 events

## Agent
- **invoicing-agent** — Invoice Drafting Copilot
- Owner: AP Team Lead (demo) · Domain: finance · Status: active
- Manifest: `C:/Users/donal/My Drive/Spin State Labs/Projects/FORCE-FIELD/field-platform/integration/demo/manifests/invoicing-agent.yaml`

## Who granted authority
| Token | Granted by | Scope | Issued | Expires | Revoked |
|---|---|---|---|---|---|
| `a32da003…` | Controller, Spin State Labs (demo) | read timesheets, draft invoices | 2026-08-29T14:07:28 | 2026-08-29T15:07:28 | no |

## What ran (timeline)
- `2026-08-29T14:07:28` **delegation.mint** — token a32da003… minted by Controller, Spin State Labs (demo) scope=['read timesheets', 'draft invoices']
- `2026-08-29T14:07:31` **conformance.allow** — ALLOW 'read timesheets'
- `2026-08-29T14:07:31` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-29T14:07:31` **spend.recorded** — spend.recorded {'event_id': 'd71bdb48-ac08-46fa-b427-b4e129f1655c', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-29T14:07:31` **usage.recorded** — usage.recorded
- `2026-08-29T14:07:31` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-29T14:07:32` **spend.recorded** — spend.recorded {'event_id': 'f7f14030-7c56-4df9-8a87-8ced60e61485', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-29T14:07:32` **usage.recorded** — usage.recorded
- `2026-08-29T14:07:32` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-29T14:07:32` **spend.recorded** — spend.recorded {'event_id': 'b99cf05b-4e30-4f25-b439-5e1f260e7cb9', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-29T14:07:32` **usage.recorded** — usage.recorded
- `2026-08-29T14:07:33` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-29T14:07:33` **spend.recorded** — spend.recorded {'event_id': 'c4eeca4b-0901-4f81-8b3b-3b4ddcbdfeb0', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-29T14:07:33` **spend.escalate** — spend.escalate {'escalation_id': '067a119b-14ab-40f4-8dfa-3eedad01cc4e', 'kind': 'cents', 'spent': 48001, 'limit': 50000}
- `2026-08-29T14:07:33` **usage.recorded** — usage.recorded
- `2026-08-29T14:07:33` **conformance.escalate** — ESCALATE 'draft invoices' [E.spend_threshold]
- `2026-08-29T14:07:33` **conformance.block** — BLOCK 'transfer funds' [D.scope]
- `2026-08-29T14:07:33` **usage.recorded** — usage.recorded
- `2026-08-29T14:07:33` **usage.rogue_model** — usage.rogue_model
- `2026-08-29T14:07:35` **kill.drill.start** — kill.drill.start by CISO on-call (demo) (scheduled drill)
- `2026-08-29T14:07:35` **kill.drill.complete** — kill.drill.complete by CISO on-call (demo) ()
- `2026-08-29T14:07:36` **kill.agent** — kill.agent by CISO on-call (demo) (containment demo)
- `2026-08-29T14:07:40` **kill.revive** — kill.revive by CISO on-call (demo) (post-incident revive)

## Which clause failed first
- `E.spend_threshold` at `2026-08-29T14:07:33` — ESCALATE 'draft invoices' [E.spend_threshold]

## Event counts
- conformance.allow: 5
- conformance.block: 1
- conformance.escalate: 1
- delegation.mint: 1
- kill.agent: 1
- kill.drill.complete: 1
- kill.drill.start: 1
- kill.revive: 1
- spend.escalate: 1
- spend.recorded: 4
- usage.recorded: 5
- usage.rogue_model: 1

## RACI
| Role | Party |
|---|---|
| Responsible | AP Team Lead (demo) (agent owner) |
| Accountable | Controller, Spin State Labs (demo) (grantor) |
| Consulted | CISO / CFO (enforcement) |
| Informed | CEO / board (attestation-reporter) |

---
*Method:* deterministic query engine v0.1 over sealed-ledger + agent-registry + delegation-authority; no LLM, no narration