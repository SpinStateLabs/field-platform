# lifecycle-manager

Authority hygiene as a scheduled job. Sweeps the registry and
delegation-authority for the three ways agents rot — **expiring
authorities**, **re-attestation due**, and **orphans** (owner not on the
human roster) — escalating each finding to the ledger. FIELD letters
**I + D**. Exec owners: **CIO / CHRO**.

The CHRO is in the loop for a reason: agents get orphaned when *people*
leave. The roster (`owners.csv`) is HR's export, not IT's.

## CLI (the scheduled-job path)

```
lifecycle sweep --roster owners.csv \
  [--expiry-days 30] [--reattest-days 90] \
  [--auto-kill-orphans] [--operator "CHRO quarterly sweep"] \
  [--markdown report.md]
```

Exit 0 = clean, 3 = findings (wire into Task Scheduler / cron; alert on 3).
`owners.csv` needs a header with an `owner` column; matching is
case-insensitive on the full owner string.

## API

```
lifecycle serve [--host 127.0.0.1] [--port 8012] [--roster owners.csv] [--every 86400]
```

| Route | Method | What |
|---|---|---|
| `/health` | GET | open; reports `roster_configured` and `every` |
| `/sweep` | POST | run a sweep now; body `{roster_csv?, expiry_days?, reattest_days?, operator?, auto_kill_orphans?}` (unknown keys ⇒ 422) |
| `/findings` | GET | the last sweep report (with its `swept_at`), or 404 before any sweep |

Roster resolution: the request's `roster_csv`, else the file at
`FIELD_LIFECYCLE_ROSTER`. With neither, `POST /sweep` answers **503** — an
empty roster would orphan every agent, so refusing is the safe answer.

`--every N` (env `FIELD_LIFECYCLE_EVERY`, 0 = off) runs a sweep in a
background thread, first tick **after** the interval so container start never
depends on a roster being present. A tick with no roster records a skip
(`lifecycle.tick_skipped` on the ledger plus a `/findings` marker) rather than
sweeping an empty roster; a tick that raises is logged and the loop continues.
**The scheduler never arms auto-kill** — that needs an explicit `true` in a
request body, and no environment variable can set it.

Env: `FIELD_LIFECYCLE_ROSTER`, `FIELD_LIFECYCLE_EVERY`, `FIELD_LIFECYCLE_URL`
(callers), plus the usual `FIELD_REGISTRY_URL` / `FIELD_DELEGATION_URL` /
`FIELD_LEDGER_URL` / `FIELD_KILLSWITCH_URL` and `FIELD_SHARED_SECRET`.

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
| Auto-kill cannot be armed over HTTP except by an explicit body flag | **Enforced in code** | adversarial test: no flag ⇒ orphan stays `active`, kill spy at zero; grep-guard: no `AUTO_KILL` env lookup exists |
| A sweep with no roster refuses (503) instead of sweeping an empty one | **Enforced in code** | test: 503, nothing ledgered — an empty roster would orphan every agent |
| Scheduler thread fires on the configured interval | **Enforced in code** when `--every`/`FIELD_LIFECYCLE_EVERY` **and** a roster are set | injected-sleep tests: first tick after the interval, a raising tick does not stop the loop, a roster-less tick records a skip |
| The roster is current and complete | **Declared only** | the sweep is as good as the CSV HR exports |
| Re-attestation actually happens after the flag | **Declared only** | the sweep reports staleness; humans attest |
| The sweep is actually running on the estate | **Declared only** | until a `swept_at` from that estate's `GET /findings` is on record — both estates run pre-v1.2 images (needs redeploy by Don) |

## LIMITS

- Re-attestation uses the registry record's `updated_at` as a proxy for
  "someone looked at this" — any registry write resets it, which is honest
  but coarse. A dedicated `attested_at` field is the known refinement.
- Owner matching is exact-string (case-insensitive), not identity-resolved:
  "J. Smith" vs "Jane Smith" are different people to this sweep.
- Auto-kill only touches `active` orphans; killed/retired agents are
  reported but untouched.
- The scheduler is in-process and its state is not persisted: a restart
  restarts the interval, and `swept_at` in `GET /findings` is the only
  evidence a sweep actually ran. It proves a run, never a cadence.
- `POST /sweep` is synchronous: a sweep of a large estate holds the request
  open (the CLI remains the path for long or scripted sweeps).
- The served sweep reaches the registry, delegation and ledger with the
  caller's estate credentials; on a secret estate every route except
  `/health` needs `x-field-auth`, so a browser cannot drive it.
