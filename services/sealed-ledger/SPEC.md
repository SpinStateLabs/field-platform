# SPEC — sealed-ledger

**Purpose:** The platform's immutable audit trail. Append-only event API where
every event is sha-256-chained to the previous one; verification walks the
chain and reports the first break; auditor export produces a JSONL copy plus
a verification summary.

**Exec owner:** CFO / audit.

**FIELD letter:** L — Ledger.

**v0.1 scope**
- JSONL store; append serialized under a lock; flush+fsync on append; head
  hash recovered on restart.
- FastAPI: POST/GET `/events`, GET `/verify`, POST `/export`, GET `/health`.
- CLI: `ledger append | verify | export | serve`.
- Tamper tests: mutate a middle record on disk → detection at that index;
  delete a middle record → link break at that index.

**Explicit non-goals (v0.1)**
- No Merkle proofs, no signatures, no external anchoring.
- No retention enforcement (manifest `retention_days` is declared only).
- No API authentication (localhost demo trust).
- No storage backend other than local JSONL.
