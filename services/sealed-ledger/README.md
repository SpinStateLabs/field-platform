# sealed-ledger

Append-only, sha-256 hash-chained event ledger. FIELD letter **L** (Ledger).
Exec owner: **CFO / audit**.

Every governance-relevant event on the platform — actions, blocks,
escalations, token mints and revocations, kills, spends — lands here as a
chained record. `verify` walks the chain and reports the **first break**.

## API

| Endpoint | Method | Purpose |
|---|---|---|
| `/events` | POST | Append an event (`event_type`, `agent_id`, `payload`) |
| `/events` | GET | Filtered read: `agent_id`, `event_type`, `since`, `until`, `limit` |
| `/verify` | GET | Walk the chain; report first break index + reason |
| `/export` | POST | Auditor export: JSONL copy + verification summary |
| `/health` | GET | Liveness + event count + head hash (sentinel uses this) |

## CLI

```
ledger append <event_type> [--payload JSON] [--agent-id ID] [--path FILE]
ledger verify [--path FILE]        # exit 1 on first break
ledger export [--out-dir DIR]
ledger serve [--host H] [--port 8002]
```

## Enforced vs. Declared

| Guarantee | Status | How |
|---|---|---|
| Every event is hash-linked to its predecessor | **Enforced in code** | `store.append` seals under a lock; genesis links to 64 zeros |
| Mutation/deletion of any past record is detectable | **Enforced in code** | `verify` recomputes every hash + link; adversarial tests mutate and delete mid-chain records on disk and prove detection |
| Appends are durable when acknowledged | **Enforced in code** | flush + fsync before returning |
| Auditor export reflects the chain it claims to | **Enforced in code** | export embeds a fresh verification result |
| Nobody can rewrite history *undetectably* | **Enforced in code** | that's the chain |
| Full-history rewrites are detectable against anchors | **Enforced in code** | `ledger anchor` pins (length, head hash); `verify --anchors` demands the chain still contain them — adversarial test proves a self-consistent forgery passes plain verify but fails the anchor check. Signed anchors (Ed25519) make the anchor file itself tamper-evident |
| Nobody can rewrite history *at all* | **Declared only** | filesystem write access defeats append-only-ness; WORM storage + off-box (or public-chain) anchor placement is deployment responsibility |
| Signatures / authorship of events | **Declared only** | v0.1 events are unsigned; any writer with API access is trusted |
| Retention periods in manifests | **Declared only** | nothing deletes or holds data on a schedule yet |

## LIMITS

- Single-writer per file: the append lock is per-process. Run one instance
  per ledger file (the docker-compose demo does).
- Chain is linear sha-256, not Merkle. A full-chain forgery is caught by
  `verify --anchors` — but only if the anchor file lives where the attacker
  can't reach it. Ship it off-box on every `ledger anchor` run, or publish
  each anchor record to a public blockchain (OpenTimestamps-style — the
  record is one small JSON object). An anchor on the same disk as the
  ledger protects against nothing.
- Reads scan the file (no index). Fine for demo scale; SQLite index is a
  later milestone.
- No authn/authz on the API in v0.1 — localhost trust (STATE.md OQ-1).
