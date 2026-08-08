# incident-replay

Deterministic incident reconstruction. Given a time window and an agent id,
answer the three questions every incident review starts with — **who granted
authority, what ran, which clause failed** — as a RACI-ready post-mortem.
FIELD letter **L** (Ledger). Exec owner: **CISO**.

## API & CLI

`POST /replay` `{agent_id, since, until}` → structured post-mortem ·
`POST /replay/markdown` → the same as markdown · `GET /health`

```
replay run <agent-id> --since 2026-08-08T00:00:00Z --until 2026-08-09T00:00:00Z [--markdown pm.md]
replay serve [--port 8007]
```

## What the report contains

- **Ledger integrity banner** — the chain is verified before anything is
  reported; a broken chain brands the whole report INTEGRITY FAILED.
- **Agent** — registry record (owner, domain, status, manifest ref).
- **Who granted authority** — every delegation grant overlapping the window
  (grantor, scope, expiry, revocation).
- **What ran** — chronological ledger timeline with event hashes.
- **Which clause failed first** — first BLOCK/ESCALATE with its clause id.
- **RACI** — Responsible: agent owner · Accountable: grantor · Consulted:
  the exec that owns the failed clause's FIELD letter · Informed: CEO/board.

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Every number/line is a query result from ledger+registry+delegation | **Enforced in code** | pure query engine; `method` field says so on every report |
| Tampered ledgers cannot produce a clean report | **Enforced in code** | `/verify` runs first; adversarial test edits the trail and asserts the FAILED banner |
| Window filtering is exact (ISO interval, inclusive) | **Enforced in code** | test |
| No LLM in the report path | **Enforced in code** | there is simply no LLM dependency; optional narration would be a separate, labeled layer (not in v0.1) |
| The trail is *complete* (nothing acted without logging) | **Declared only** (here) | completeness is the sentinel's fail-closed job; replay reports what the ledger holds |

## LIMITS

- Replay is only as complete as the ledger: actions taken outside the
  sentinel/decorator perimeter never became events and cannot be replayed.
- RACI "Consulted" comes from a static clause-letter → exec map; org charts
  differ — treat it as a default, not an org lookup.
- Grant/window overlap uses ISO-string comparison (all writers emit UTC ISO;
  mixed-offset timestamps from foreign writers could mis-order).
- No API authentication in v0.1 — localhost trust (STATE.md OQ-1).
