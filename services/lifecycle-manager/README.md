# lifecycle-manager

Authority hygiene as a scheduled job. Sweeps the registry and
delegation-authority for the three ways agents rot — **expiring
authorities**, **re-attestation due**, and **orphans** (owner not on the
human roster) — escalating each finding to the ledger. FIELD letters
**I + D**. Exec owners: **CIO / CHRO**.

The CHRO is in the loop for a reason: agents get orphaned when *people*
leave. The roster (`owners.csv`) is HR's export, not IT's.

## CLI (a job, not a daemon)

```
lifecycle sweep --roster owners.csv \
  [--expiry-days 30] [--reattest-days 90] \
  [--auto-kill-orphans] [--operator "CHRO quarterly sweep"] \
  [--markdown report.md]
```

Exit 0 = clean, 3 = findings (wire into Task Scheduler / cron; alert on 3).
`owners.csv` needs a header with an `owner` column; matching is
case-insensitive on the full owner string.

## Findings → ledger events

| Finding | Ledger event | Default action |
|---|---|---|
| Token lapsing within horizon | `lifecycle.expiring_authority` | report (renew or let die — deliberately) |
| Registry record stale past re-attestation period | `lifecycle.reattestation_due` | report |
| Owner not on roster | `lifecycle.orphan` | **escalate only** — auto-kill requires the flag |

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Expiring/stale/orphaned authority is detected deterministically | **Enforced in code** | date arithmetic + roster set membership; tests |
| Auto-kill NEVER happens without the explicit flag | **Enforced in code** | adversarial test: flag off ⇒ orphan stays active |
| Auto-kills go through kill-switch and land on the ledger | **Enforced in code** | reason string names the sweep; test |
| Sweeps are idempotent (no duplicate kills on re-run) | **Enforced in code** | second sweep sees status ≠ active; test |
| The roster is current and complete | **Declared only** | the sweep is as good as the CSV HR exports |
| Re-attestation actually happens after the flag | **Declared only** | the sweep reports staleness; humans attest |
| The job actually runs on schedule | **Declared only** | scheduling belongs to Task Scheduler/cron/CI |

## LIMITS

- Re-attestation uses the registry record's `updated_at` as a proxy for
  "someone looked at this" — any registry write resets it, which is honest
  but coarse. A dedicated `attested_at` field is the known refinement.
- Owner matching is exact-string (case-insensitive), not identity-resolved:
  "J. Smith" vs "Jane Smith" are different people to this sweep.
- Auto-kill only touches `active` orphans; killed/retired agents are
  reported but untouched.
- No API surface in v0.1 — deliberately CLI-only (a job you schedule and
  audit, not an endpoint someone forgets is open).
