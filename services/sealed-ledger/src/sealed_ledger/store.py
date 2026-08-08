"""JSONL-backed hash-chained ledger store.

ENFORCED: every append links to the previous event's hash; verification
walks the full chain and reports the first break. Appends are serialized
under a process lock and flushed+fsynced before returning.

DECLARED only: append-only-ness of the file itself. Any process with write
access to the filesystem can rewrite history — the chain guarantees such
tampering is *detectable*, not *impossible*.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel

from field_core.ledger import (
    GENESIS_HASH,
    ChainVerification,
    LedgerEvent,
    make_event,
    verify_chain,
)


class ExportSummary(BaseModel):
    exported_at: str
    path: str
    event_count: int
    head_hash: str
    first_ts: str | None = None
    last_ts: str | None = None
    event_types: dict[str, int]
    agents: dict[str, int]
    verification: ChainVerification


class LedgerStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._head_hash = self._recover_head()

    def _recover_head(self) -> str:
        if not self.path.exists():
            return GENESIS_HASH
        head = GENESIS_HASH
        for event in self.iter_events():
            head = event.hash
        return head

    def iter_events(self) -> Iterator[LedgerEvent]:
        if not self.path.exists():
            return
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield LedgerEvent.model_validate(json.loads(line))

    @property
    def head_hash(self) -> str:
        return self._head_hash

    def append(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        agent_id: str | None = None,
    ) -> LedgerEvent:
        with self._lock:
            event = make_event(
                event_type=event_type,
                payload=payload,
                prev_hash=self._head_hash,
                agent_id=agent_id,
            )
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(event.model_dump_json() + "\n")
                fh.flush()
                os.fsync(fh.fileno())
            self._head_hash = event.hash
            return event

    def events(
        self,
        agent_id: str | None = None,
        event_type: str | None = None,
        since: str | None = None,
        until: str | None = None,
        limit: int | None = None,
    ) -> list[LedgerEvent]:
        out = []
        for event in self.iter_events():
            if agent_id is not None and event.agent_id != agent_id:
                continue
            if event_type is not None and event.event_type != event_type:
                continue
            if since is not None and event.ts < since:
                continue
            if until is not None and event.ts > until:
                continue
            out.append(event)
        if limit is not None:
            out = out[-limit:]
        return out

    def verify(self) -> ChainVerification:
        return verify_chain(self.iter_events())

    def export(self, out_dir: str | Path) -> ExportSummary:
        """Auditor export: copy of the JSONL + a summary with verification."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        jsonl_out = out_dir / f"ledger-export-{stamp}.jsonl"

        events = list(self.iter_events())
        with jsonl_out.open("w", encoding="utf-8") as fh:
            for event in events:
                fh.write(event.model_dump_json() + "\n")

        type_counts: dict[str, int] = {}
        agent_counts: dict[str, int] = {}
        for event in events:
            type_counts[event.event_type] = type_counts.get(event.event_type, 0) + 1
            key = event.agent_id or "<none>"
            agent_counts[key] = agent_counts.get(key, 0) + 1

        summary = ExportSummary(
            exported_at=datetime.now(timezone.utc).isoformat(),
            path=str(jsonl_out),
            event_count=len(events),
            head_hash=self._head_hash,
            first_ts=events[0].ts if events else None,
            last_ts=events[-1].ts if events else None,
            event_types=type_counts,
            agents=agent_counts,
            verification=verify_chain(events),
        )
        summary_path = out_dir / f"ledger-export-{stamp}.summary.json"
        summary_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
        return summary
