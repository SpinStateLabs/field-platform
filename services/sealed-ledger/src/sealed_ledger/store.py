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
from pathlib import Path
from typing import Any, Iterator

from field_core.ledger import (
    GENESIS_HASH,
    ChainVerification,
    LedgerEvent,
    make_event,
    verify_chain,
)
from sealed_ledger.bundle import ExportSummary, write_bundle
from sealed_ledger.filters import EventFilter, InvalidTimeBound

__all__ = ["ExportSummary", "InvalidTimeBound", "LedgerStore"]


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
        """Filtered read. ``since``/``until`` are inclusive ISO 8601 instants
        (compared as datetimes, not strings); a bad bound raises
        ``InvalidTimeBound`` before the file is read."""
        event_filter = EventFilter(
            agent_id=agent_id, event_type=event_type, since=since, until=until
        )
        out = []
        for index, event in enumerate(self.iter_events()):
            if event_filter.matches(index, event):
                out.append(event)
        if limit is not None:
            out = out[-limit:]
        return out

    def verify(self) -> ChainVerification:
        return verify_chain(self.iter_events())

    def export(
        self,
        out_dir: str | Path,
        *,
        since: str | None = None,
        until: str | None = None,
        agent_id: str | None = None,
        event_type: str | None = None,
        private_key_pem: str | None = None,
    ) -> ExportSummary:
        """Auditor export bundle ``out_dir/<stamp>/`` (see ``sealed_ledger.bundle``).

        The chain is read ONCE; the filters, the spine, ``head_hash`` and the
        full-chain verification all come from that one read (never from the
        cached head). ``private_key_pem`` signs summary + chain_proof; the
        served route never passes one.
        """
        event_filter = EventFilter(
            agent_id=agent_id, event_type=event_type, since=since, until=until
        )
        snapshot = list(self.iter_events())
        return write_bundle(out_dir, snapshot, event_filter, private_key_pem=private_key_pem)
