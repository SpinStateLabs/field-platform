# Post-mortem — invoicing-agent

*Window:* `2020-01-01T00:00:00+00:00` → `2030-01-01T00:00:00+00:00` · *Generated:* 2026-08-10T14:08:44.864321+00:00
*Ledger integrity:* OK — chain intact over 15 events

## Agent
- **invoicing-agent** — Invoice Drafting Copilot
- Owner: AP Team Lead (demo) · Domain: finance · Status: active
- Manifest: `C:/Users/donal/My Drive/Spin State Labs/Projects/FORCE-FIELD/field-platform/integration/demo/manifests/invoicing-agent.yaml`

## Who granted authority
| Token | Granted by | Scope | Issued | Expires | Revoked |
|---|---|---|---|---|---|
| `36bd7a29…` | Controller, Spin State Labs (demo) | read timesheets, draft invoices | 2026-08-10T14:08:34 | 2026-08-10T15:08:34 | no |

## What ran (timeline)
- `2026-08-10T14:08:34` **delegation.mint** — token 36bd7a29… minted by Controller, Spin State Labs (demo) scope=['read timesheets', 'draft invoices']
- `2026-08-10T14:08:37` **conformance.allow** — ALLOW 'read timesheets'
- `2026-08-10T14:08:37` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-10T14:08:38` **spend.recorded** — spend.recorded {'event_id': '0ab01a8a-1566-4235-8420-f5a6c01cea49', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-10T14:08:38` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-10T14:08:39` **spend.recorded** — spend.recorded {'event_id': '7e3ea261-b9cb-4aad-a4da-615e4ad26349', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-10T14:08:39` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-10T14:08:39` **spend.recorded** — spend.recorded {'event_id': '2c7b7b73-a925-4c08-9b5c-f8ca21a87ccd', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-10T14:08:40` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-10T14:08:40` **spend.recorded** — spend.recorded {'event_id': '9da6958b-9a64-48eb-8e35-4d480facba7e', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-10T14:08:40` **spend.escalate** — spend.escalate {'escalation_id': 'd98bf318-1f36-476d-8d07-8662987d677b', 'kind': 'cents', 'spent': 48000, 'limit': 50000}
- `2026-08-10T14:08:41` **conformance.escalate** — ESCALATE 'draft invoices' [E.spend_threshold]
- `2026-08-10T14:08:42` **conformance.block** — BLOCK 'transfer funds' [D.scope]
- `2026-08-10T14:08:43` **kill.drill.start** — kill.drill.start by CISO on-call (demo) (scheduled drill)
- `2026-08-10T14:08:43` **kill.drill.complete** — kill.drill.complete by CISO on-call (demo) ()

## Which clause failed first
- `E.spend_threshold` at `2026-08-10T14:08:41` — ESCALATE 'draft invoices' [E.spend_threshold]

## Event counts
- conformance.allow: 5
- conformance.block: 1
- conformance.escalate: 1
- delegation.mint: 1
- kill.drill.complete: 1
- kill.drill.start: 1
- spend.escalate: 1
- spend.recorded: 4

## RACI
| Role | Party |
|---|---|
| Responsible | AP Team Lead (demo) (agent owner) |
| Accountable | Controller, Spin State Labs (demo) (grantor) |
| Consulted | CISO / CFO (enforcement) |
| Informed | CEO / board (attestation-reporter) |

---
*Method:* deterministic query engine v0.1 over sealed-ledger + agent-registry + delegation-authority; no LLM, no narration