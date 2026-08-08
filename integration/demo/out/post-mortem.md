# Post-mortem — invoicing-agent

*Window:* `2020-01-01T00:00:00+00:00` → `2030-01-01T00:00:00+00:00` · *Generated:* 2026-08-08T08:05:07.054085+00:00
*Ledger integrity:* OK — chain intact over 15 events

## Agent
- **invoicing-agent** — Invoice Drafting Copilot
- Owner: AP Team Lead (demo) · Domain: finance · Status: active
- Manifest: `C:/Users/donal/My Drive/Spin State Labs/Projects/FORCE-FIELD/field-platform/integration/demo/manifests/invoicing-agent.yaml`

## Who granted authority
| Token | Granted by | Scope | Issued | Expires | Revoked |
|---|---|---|---|---|---|
| `ceb5f2d7…` | Controller, Spin State Labs (demo) | read timesheets, draft invoices | 2026-08-08T08:04:58 | 2026-08-08T09:04:58 | no |

## What ran (timeline)
- `2026-08-08T08:04:58` **delegation.mint** — token ceb5f2d7… minted by Controller, Spin State Labs (demo) scope=['read timesheets', 'draft invoices']
- `2026-08-08T08:05:00` **conformance.allow** — ALLOW 'read timesheets'
- `2026-08-08T08:05:00` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-08T08:05:01` **spend.recorded** — spend.recorded {'event_id': 'e4504865-8292-4a63-b52e-7fd397564d6e', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-08T08:05:01` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-08T08:05:02` **spend.recorded** — spend.recorded {'event_id': 'c22bea15-a57c-4bd9-85da-ee18b7cf6d8b', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-08T08:05:02` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-08T08:05:03` **spend.recorded** — spend.recorded {'event_id': '19554e59-0900-44cc-88b8-a4059ccaec34', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-08T08:05:03` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-08T08:05:03` **spend.recorded** — spend.recorded {'event_id': 'd0f4e2c9-be35-4f7a-ae9f-d69b25292409', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-08T08:05:03` **spend.escalate** — spend.escalate {'escalation_id': '09146a1c-eda8-44ae-ae17-e98da32dd1e1', 'kind': 'cents', 'spent': 48000, 'limit': 50000}
- `2026-08-08T08:05:04` **conformance.escalate** — ESCALATE 'draft invoices' [E.spend_threshold]
- `2026-08-08T08:05:04` **conformance.block** — BLOCK 'transfer funds' [D.scope]
- `2026-08-08T08:05:05` **kill.drill.start** — kill.drill.start by CISO on-call (demo) (scheduled drill)
- `2026-08-08T08:05:05` **kill.drill.complete** — kill.drill.complete by CISO on-call (demo) ()

## Which clause failed first
- `E.spend_threshold` at `2026-08-08T08:05:04` — ESCALATE 'draft invoices' [E.spend_threshold]

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