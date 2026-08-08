# Post-mortem — invoicing-agent

*Window:* `2020-01-01T00:00:00+00:00` → `2030-01-01T00:00:00+00:00` · *Generated:* 2026-08-08T06:58:10.534550+00:00
*Ledger integrity:* OK — chain intact over 15 events

## Agent
- **invoicing-agent** — Invoice Drafting Copilot
- Owner: AP Team Lead (demo) · Domain: finance · Status: active
- Manifest: `C:/Users/donal/My Drive/Spin State Labs/Projects/FORCE-FIELD/field-platform/integration/demo/manifests/invoicing-agent.yaml`

## Who granted authority
| Token | Granted by | Scope | Issued | Expires | Revoked |
|---|---|---|---|---|---|
| `6772ce87…` | Controller, Spin State Labs (demo) | read timesheets, draft invoices | 2026-08-08T06:58:02 | 2026-08-08T07:58:02 | no |

## What ran (timeline)
- `2026-08-08T06:58:02` **delegation.mint** — token 6772ce87… minted by Controller, Spin State Labs (demo) scope=['read timesheets', 'draft invoices']
- `2026-08-08T06:58:04` **conformance.allow** — ALLOW 'read timesheets'
- `2026-08-08T06:58:04` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-08T06:58:05` **spend.recorded** — spend.recorded {'event_id': 'b96a317d-5c8e-4d31-9472-7ab9ceae105b', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-08T06:58:05` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-08T06:58:05` **spend.recorded** — spend.recorded {'event_id': '1b2ab78a-58d8-4cf4-bd90-b880b46fe17a', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-08T06:58:06` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-08T06:58:06` **spend.recorded** — spend.recorded {'event_id': '99a07e49-0836-46ac-8480-a406e596153e', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-08T06:58:07` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-08T06:58:07` **spend.recorded** — spend.recorded {'event_id': '672c27a0-74aa-441f-a19a-5a1fd6d76d87', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-08T06:58:07` **spend.escalate** — spend.escalate {'escalation_id': '6688c378-ff1a-45a1-8e36-9d9d2a5634e9', 'kind': 'cents', 'spent': 48000, 'limit': 50000}
- `2026-08-08T06:58:07` **conformance.escalate** — ESCALATE 'draft invoices' [E.spend_threshold]
- `2026-08-08T06:58:08` **conformance.block** — BLOCK 'transfer funds' [D.scope]
- `2026-08-08T06:58:09` **kill.drill.start** — kill.drill.start by CISO on-call (demo) (scheduled drill)
- `2026-08-08T06:58:09` **kill.drill.complete** — kill.drill.complete by CISO on-call (demo) ()

## Which clause failed first
- `E.spend_threshold` at `2026-08-08T06:58:07` — ESCALATE 'draft invoices' [E.spend_threshold]

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