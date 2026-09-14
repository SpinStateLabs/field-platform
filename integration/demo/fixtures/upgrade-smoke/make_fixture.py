"""Write an OLD-schema FIELD /data for CI's compose-upgrade-smoke (v1.2 Phase C).

    python make_fixture.py DATA_DIR

Writes what a pre-Phase-C estate has on its field-data volume, so the job can
start the CURRENT images (GB10 topology) on it and prove the upgrade path:

- ledger/events.jsonl: a pre-C2 SINGLE-FILE ledger, and the ledger directory
  holds that one file and nothing else, as a pre-C2 estate's does. Written with
  the current sealed-ledger LedgerStore without ever rotating (one event per
  line, `LedgerEvent.model_dump_json()`, no segments journal; refused if a
  journal appears). The writer lock file (.events.jsonl.lock) that a C2 writer
  leaves is removed, so the upgraded ledger's first open sees no lock file,
  exactly like the GB10's. That the lines are byte-for-byte what the db5ad33
  store writes and reads back is checked in the fix-round evidence, not here:
  CI's shallow checkout has no db5ad33 to import.
- registry/agents.sqlite3: the pre-v1.2 registry, 8 columns, created with the
  DDL and positional INSERT of ad7a79c (the image the GB10 ran before X0) —
  NOT the current store, which would add attested_at/attested_by. The current
  registry must migrate it on first start and still serve the old row.
- governor/spend.sqlite3: the pre-D1 spend-governor, created with the `_SCHEMA`
  DDL and the positional INSERTs of 3aa90ff (unchanged since 88e44aa): the
  7-column `spend` table with no `action`/`source`. One `total` cap and one
  spend row for the legacy agent. The D1 governor migrates it at its first
  open (PRAGMA -> ALTER TABLE) and must still serve the old row as a
  self-reported, unattributed action.
- manifests/: the fixture manifest, on the data volume where pre-Phase-C
  estates kept them. On the GB10 topology manifests-admin seeds the read-only
  field-manifests volume from here.
- doa-roster.yaml and owners.csv at the A3 / A1 arming paths, for
  FIELD_DOA_ROSTER=/data/doa-roster.yaml and FIELD_LIFECYCLE_ROSTER=/data/owners.csv.

Refuses (exit 2) to write into a DATA_DIR that already has a ledger, a
registry or a governor: it must never be pointed at real estate data. The LAST line of
stdout is the JSON pin of the fixture ledger ({event_count, head_index,
head_hash}); the job asserts the upgraded ledger still has that head at that
index. Local twin of the job (everything but docker):
tools/tests/test_upgrade_smoke_fixture.py.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEGACY_AGENT = "legacy-fixture-agent"

#: Verbatim from services/spend-governor/src/spend_governor/core.py ``_SCHEMA`` at
#: 3aa90ff (identical at 88e44aa), the last governor before D1: ``spend`` has 7
#: columns. The current store adds ``action``/``source`` at open.
PRE_D1_GOVERNOR_SCHEMA = """
CREATE TABLE IF NOT EXISTS caps (
    agent_id TEXT PRIMARY KEY, currency TEXT, limit_cents INTEGER,
    token_limit INTEGER, action_limit INTEGER, period TEXT,
    escalate_at_pct INTEGER, on_breach TEXT
);
CREATE TABLE IF NOT EXISTS spend (
    event_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, ts TEXT NOT NULL,
    cents INTEGER NOT NULL, tokens INTEGER NOT NULL, actions INTEGER NOT NULL,
    note TEXT
);
CREATE INDEX IF NOT EXISTS idx_spend_agent_ts ON spend (agent_id, ts);
CREATE TABLE IF NOT EXISTS escalations (
    escalation_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, ts TEXT NOT NULL,
    kind TEXT NOT NULL, spent INTEGER NOT NULL, "limit" INTEGER NOT NULL,
    pct INTEGER NOT NULL, resolved INTEGER NOT NULL DEFAULT 0, resolved_by TEXT
);
CREATE TABLE IF NOT EXISTS usage (
    event_id TEXT PRIMARY KEY, agent_id TEXT NOT NULL, ts TEXT NOT NULL,
    model TEXT NOT NULL, input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL, cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cost_units INTEGER, priced INTEGER NOT NULL DEFAULT 1, note TEXT
);
CREATE INDEX IF NOT EXISTS idx_usage_agent_ts ON usage (agent_id, ts);
CREATE TABLE IF NOT EXISTS usage_policies (
    agent_id TEXT PRIMARY KEY, allowed_models TEXT NOT NULL,
    token_rate_limit INTEGER, rate_window_seconds INTEGER NOT NULL DEFAULT 3600
);
"""
#: The legacy agent's pre-D1 cap and its one spend row (what upgrade_flow.py reads back).
LEGACY_CAP_CENTS = 10_000
LEGACY_SPEND_CENTS = 250

#: Verbatim from services/agent-registry/src/agent_registry/store.py at ad7a79c.
PRE_V12_REGISTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    agent_id     TEXT PRIMARY KEY,
    name         TEXT NOT NULL,
    owner        TEXT NOT NULL,
    domain       TEXT NOT NULL DEFAULT 'general',
    manifest_ref TEXT,
    status       TEXT NOT NULL DEFAULT 'active',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
"""


def _refuse(message: str) -> "None":
    print(f"refusing: {message}", file=sys.stderr)
    raise SystemExit(2)


def write_fixture(data: Path) -> dict:
    from sealed_ledger.store import LedgerStore, journal_path_for

    ledger_file = data / "ledger" / "events.jsonl"
    registry_file = data / "registry" / "agents.sqlite3"
    governor_file = data / "governor" / "spend.sqlite3"
    for existing in (ledger_file, registry_file, governor_file):
        if existing.exists():
            _refuse(f"{existing} exists - never write the fixture over estate data")

    created = "2026-08-08T12:00:00+00:00"
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(registry_file))
    with conn:
        conn.executescript(PRE_V12_REGISTRY_SCHEMA)
        conn.execute(
            "INSERT INTO agents VALUES (?,?,?,?,?,?,?,?)",
            (LEGACY_AGENT, "Legacy fixture agent", "FIELD CI (compose-upgrade-smoke)",
             "ci", None, "active", created, created),
        )
    conn.close()

    governor_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(governor_file))
    with conn:
        conn.executescript(PRE_D1_GOVERNOR_SCHEMA)
        # the pre-D1 GovernorStore.set_cap / record_spend positional INSERTs
        conn.execute("INSERT OR REPLACE INTO caps VALUES (?,?,?,?,?,?,?,?)",
                     (LEGACY_AGENT, "USD", LEGACY_CAP_CENTS, None, None, "total", 80, "halt"))
        conn.execute("INSERT INTO spend VALUES (?,?,?,?,?,?,?)",
                     ("pre-d1-fixture-spend-0001", LEGACY_AGENT, created, LEGACY_SPEND_CENTS, 0, 1,
                      "pre-D1 fixture row (compose-upgrade-smoke)"))
    conn.close()

    store = LedgerStore(ledger_file)
    store.append("registry.registered", {"name": "Legacy fixture agent",
                                         "owner": "FIELD CI (compose-upgrade-smoke)",
                                         "domain": "ci", "manifest_ref": None},
                 agent_id=LEGACY_AGENT)
    for i in range(4):
        store.append("fixture.pre_upgrade", {"i": i, "written_at": datetime.now(timezone.utc).isoformat()})
    if journal_path_for(ledger_file).exists():
        _refuse("a segments journal exists - this is not a pre-C2 single-file ledger")
    store.lock_path.unlink(missing_ok=True)  # released after every write; pre-C2 dirs have none
    leftovers = sorted(p.name for p in ledger_file.parent.iterdir())
    if leftovers != ["events.jsonl"]:
        _refuse(f"the ledger directory holds {leftovers}, not just events.jsonl - not a pre-C2 ledger dir")
    lines = ledger_file.read_text(encoding="utf-8").splitlines()

    (data / "manifests").mkdir(parents=True, exist_ok=True)
    for manifest in sorted((HERE / "manifests").glob("*.yaml")):
        shutil.copyfile(manifest, data / "manifests" / manifest.name)
    shutil.copyfile(HERE / "doa-roster.yaml", data / "doa-roster.yaml")
    shutil.copyfile(HERE / "owners.csv", data / "owners.csv")

    head = json.loads(lines[-1])
    return {"event_count": len(lines), "head_index": len(lines) - 1, "head_hash": head["hash"]}


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    pin = write_fixture(Path(argv[0]))
    print(f"old-schema /data written to {argv[0]}: pre-C2 single-file ledger, "
          f"pre-v1.2 registry, pre-D1 governor, manifests on the data volume, rosters")
    print(json.dumps(pin, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
