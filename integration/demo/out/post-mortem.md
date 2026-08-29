# Post-mortem — invoicing-agent

*Window:* `2020-01-01T00:00:00+00:00` → `2030-01-01T00:00:00+00:00` · *Generated:* 2026-08-29T14:46:27.113339+00:00
*Ledger integrity:* OK — chain intact over 23 events

## Agent
- **invoicing-agent** — Invoice Drafting Copilot
- Owner: AP Team Lead (demo) · Domain: finance · Status: active
- Manifest: `C:/Users/donal/My Drive/Spin State Labs/Projects/FORCE-FIELD/field-platform/integration/demo/manifests/invoicing-agent.yaml`

## Who granted authority
| Token | Granted by | Scope | Issued | Expires | Revoked |
|---|---|---|---|---|---|
| `5d1c41cc…` | Controller, Spin State Labs (demo) | read timesheets, draft invoices | 2026-08-29T14:46:11 | 2026-08-29T15:46:11 | no |

## What ran (timeline)
- `2026-08-29T14:46:11` **delegation.mint** — token 5d1c41cc… minted by Controller, Spin State Labs (demo) scope=['read timesheets', 'draft invoices']
- `2026-08-29T14:46:14` **conformance.allow** — ALLOW 'read timesheets'
- `2026-08-29T14:46:15` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-29T14:46:15` **spend.recorded** — spend.recorded {'event_id': '51dab447-d388-4ef1-8cf1-72931d272c4e', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-29T14:46:15` **usage.recorded** — usage.recorded
- `2026-08-29T14:46:16` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-29T14:46:16` **spend.recorded** — spend.recorded {'event_id': 'a04320f0-0b31-439c-8465-9c26ec7ec3ec', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-29T14:46:16` **usage.recorded** — usage.recorded
- `2026-08-29T14:46:16` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-29T14:46:16` **spend.recorded** — spend.recorded {'event_id': 'b3daa0bd-1c9f-4140-939f-e97310a5871b', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-29T14:46:16` **usage.recorded** — usage.recorded
- `2026-08-29T14:46:17` **conformance.allow** — ALLOW 'draft invoices'
- `2026-08-29T14:46:17` **spend.recorded** — spend.recorded {'event_id': 'bd29202f-83be-4cce-8bc6-b43b1e387559', 'cents': 12000, 'tokens': 0, 'actions': 1}
- `2026-08-29T14:46:17` **spend.escalate** — spend.escalate {'escalation_id': '9c83fb80-edf9-4240-85ed-a9226f5ef020', 'kind': 'cents', 'spent': 48001, 'limit': 50000}
- `2026-08-29T14:46:17` **usage.recorded** — usage.recorded
- `2026-08-29T14:46:17` **conformance.escalate** — ESCALATE 'draft invoices' [E.spend_threshold]
- `2026-08-29T14:46:18` **conformance.block** — BLOCK 'transfer funds' [D.scope]
- `2026-08-29T14:46:18` **usage.recorded** — usage.recorded
- `2026-08-29T14:46:18` **usage.rogue_model** — usage.rogue_model
- `2026-08-29T14:46:19` **kill.drill.start** — kill.drill.start by CISO on-call (demo) (scheduled drill)
- `2026-08-29T14:46:19` **kill.drill.complete** — kill.drill.complete by CISO on-call (demo) ()
- `2026-08-29T14:46:21` **kill.agent** — kill.agent by CISO on-call (demo) (containment demo)
- `2026-08-29T14:46:25` **kill.revive** — kill.revive by CISO on-call (demo) (post-incident revive)

## Which clause failed first
- `E.spend_threshold` at `2026-08-29T14:46:17` — ESCALATE 'draft invoices' [E.spend_threshold]

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