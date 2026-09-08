# agents/ — Spin State's own FIELD-governed agents (dogfood)

Source-of-truth copies of the Claude skills that run Spin State Labs' real
back-office agents under the Force Field Protocol. The account-synced skill
files (`~/.claude/skills/...`) are a read-only cache; edit HERE, then push the
change to the account skill.

| Agent id | Skill | Manifest | What it does |
|---|---|---|---|
| `ssl-timekeeping-agent` | `ssl-timekeeping-agent/SKILL.md` | `../manifests/ssl-timekeeping-agent.yaml` | drafts Don's daily timesheet, writes the per-client xlsx, keys hours into client portals (Don submits) |
| `ssl-invoicing-agent` | `ssl-invoicing-agent/SKILL.md` | `../manifests/ssl-invoicing-agent.yaml` | builds client invoices from those xlsx files, records them in Zoho Books, drafts the email text |

Both are **Claude skills**, not Python processes: they cannot import
`field_agent`. They reach the estate through `../tools/field-rest.ps1` (the
raw-REST path of `plugins/field-agent/skills/field-agent/rest-api.md`) from the
Windows PowerShell tool on rog-command. Estate: GB10 `http://10.0.0.62:18080`,
sentinel **enforce**. Operator side: `../tools/provision_ssl_agents.py`.

## Enforced vs. Declared

A governance product that overclaims has already failed. This table is exact
for a *skill* agent; compare `packages/field-agent/README.md` for the SDK.

| Guarantee | Status | How |
|---|---|---|
| A governed action the skill checks runs only on ALLOW; BLOCK / ESCALATE / unreachable sentinel stop it | **Enforced by the estate** (server verdict) + **Declared** on the client (the skill must honour the `$false` the shim returns) | sentinel `/check` in enforce mode; `field-rest.ps1` fail-closed branches |
| Out-of-scope actions (`send invoice email`, `submit for approval`, …) are BLOCK `D.scope` | **Enforced by the estate** | manifest ∩ token scope; verified by `provision_ssl_agents.py`'s never-granted probe |
| Killed or unknown agent halts at the next heartbeat / check | **Enforced by the estate** (kill-switch answers `killed=true`; sentinel BLOCKs `E.kill_switch`) — halt latency = next call, never zero | `Get-FieldHeartbeat` first in every run |
| Every check, escalation, token use and spend is on the sealed ledger | **Enforced by the estate** | hash-chained JSONL; `GET /ledger/verify` |
| Every tool call the skill makes is governed | **Declared only — cooperative perimeter** | a call made without `Invoke-FieldCheck` is invisible to FIELD; backstop: killed agents' next check BLOCKs, tokens revocable |
| Spend is metered in dollars / tokens | **Declared only — NOT metered** | Cowork exposes no token counts; the shim posts actions-only (`cents=0`). Dollar metering requires routing LLM calls through force-gateway, which a Cowork session cannot do |
| The model in use is on an allow-list | **Not declared** | no `PUT /policies` is set — the agent cannot choose its model, so an allow-list would be unverifiable |
| Token id is valid and scoped | **Enforced by the estate** (delegation-authority + sentinel); the shim only carries it | `tokens-gb10.json` outside Drive |

## Compliance self-review (checklist.md rubric, adapted to a skill agent)

`FIELD-AGENT COMPLIANCE — agents/ssl-*/SKILL.md — 2026-09-08`

- A. Liveness — A1 PASS (heartbeat is step 1 in both skills) · A2 N-A (no long loop; each governed action re-checks) · A3 PASS (killed/unreachable ⇒ stop before work; enforce posture)
- B. Actions — B1 PASS-by-instruction (every side-effectful step names its `-Action`; Declared, see table) · B2 PASS (strings verified identical between SKILL.md tables, manifests and `provision_ssl_agents.py`, which mints from the manifest) · B3 PASS (BLOCK ⇒ abandon) · B4 PASS (ESCALATE ⇒ human queue, no loop) · B5 PARTIAL (irreversible actions are absent from scope rather than flagged `irreversible=True`; REST `/check` carries no such flag)
- C. Usage — C1 FAIL-by-design (no LLM usage report possible; stated) · C2 PASS (actions metered via `/spend`) · C3 PASS (404/failure ⇒ "unmetered", never silent)
- D. Authority — D1 PASS (provisioning is a separate operator script) · D2 PASS (token from `tokens-gb10.json`, never in the skill) · D3 PASS (no secrets in these files; `FIELD_SHARED_SECRET` via env)
- E. Operator — E1 manifests validate (schema + `field validate`) · E2 caps set by `provision_ssl_agents.py` · E3 N-A (no model policy, stated) · E4 estate mode = **enforce**
- F. Honesty — F1 PASS (cooperative-perimeter line in both skills) · F2 PASS (this table) · F3 PASS (no "cannot misbehave", no instant-halt claim, no "Force Field Framework")

VERDICT: **NOT COMPLIANT under the SDK rubric (C1)** — by construction, and stated. Compliant on every item a skill agent can satisfy.
