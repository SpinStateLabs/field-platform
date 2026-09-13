"""Ledger event model and sha-256 hash-chain primitives.

ENFORCED in code: every event's ``hash`` is sha-256 over the canonical JSON
of the event minus its own hash, and carries ``prev_hash`` linking it to the
previous event (genesis links to 64 zero chars unless ``verify_chain`` is
given another ``genesis``). ``verify_chain`` walks the chain and reports the
first break. ``ChainVerification`` carries four extra keys only for a
segmented (rotated) ledger; the global index offset lives in the ledger
store, not here.

DECLARED only: durability of the underlying store. A hash chain proves
tampering happened; it cannot prevent deletion of the whole file. WORM
storage is the deployment's responsibility.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_serializer

GENESIS_HASH = "0" * 64


class LedgerEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    ts: str  # ISO 8601 UTC — stored as string so hashing is byte-stable
    event_type: str
    agent_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    prev_hash: str
    hash: str


def _canonical_bytes(record: dict[str, Any]) -> bytes:
    """Deterministic serialization: sorted keys, no whitespace, UTF-8."""
    return json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def compute_event_hash(event: LedgerEvent | dict[str, Any]) -> str:
    record = event.model_dump() if isinstance(event, LedgerEvent) else dict(event)
    record.pop("hash", None)
    return hashlib.sha256(_canonical_bytes(record)).hexdigest()


def make_event(
    event_type: str,
    payload: dict[str, Any] | None = None,
    prev_hash: str = GENESIS_HASH,
    agent_id: str | None = None,
    ts: str | None = None,
    event_id: str | None = None,
) -> LedgerEvent:
    """Build a sealed event linked to ``prev_hash``."""
    partial = {
        "event_id": event_id or str(uuid.uuid4()),
        "ts": ts or datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "agent_id": agent_id,
        "payload": payload or {},
        "prev_hash": prev_hash,
    }
    return LedgerEvent(**partial, hash=compute_event_hash(partial))


_SEGMENT_KEYS = ("segments", "archived_segments", "verified_events", "break_segment")


class ChainVerification(BaseModel):
    ok: bool
    length: int
    first_break_index: int | None = None
    reason: str | None = None
    # Segmented (rotated) ledgers only. All None on a single-file chain, and
    # then left OUT of every serialisation, so a ledger that never rotated
    # serialises to exactly the four keys above (the C1 export bundle pins
    # that dict). ``length`` and ``first_break_index`` are global indices.
    segments: int | None = None  # live segments walked (closed + open)
    archived_segments: int | None = None  # verified by journal link only
    verified_events: int | None = None  # live events whose hashes were recomputed
    break_segment: int | None = None  # the segment holding first_break_index

    # No return annotation on purpose: with one, pydantic (and so FastAPI's
    # OpenAPI) describes the response as a bare object instead of these fields.
    @model_serializer(mode="wrap")
    def _omit_segment_keys_on_single_file(self, handler):
        data = handler(self)
        if self.segments is None and isinstance(data, dict):
            for key in _SEGMENT_KEYS:
                data.pop(key, None)
        return data


def verify_chain(
    events: Iterable[LedgerEvent], genesis: str = GENESIS_HASH
) -> ChainVerification:
    """Walk the chain; report the first break (index + reason).

    ``genesis`` is the ``prev_hash`` the first event must carry. It defaults
    to 64 zeros (a chain that starts at the beginning of history); pass a
    previous head hash to verify a chain segment that continues it.
    ``first_break_index`` is always the index within ``events``.
    """
    prev_hash = genesis
    count = 0
    for i, event in enumerate(events):
        count = i + 1
        if event.prev_hash != prev_hash:
            return ChainVerification(
                ok=False,
                length=count,
                first_break_index=i,
                reason=(
                    f"link break at index {i}: prev_hash {event.prev_hash[:12]}… "
                    f"does not match previous event hash {prev_hash[:12]}…"
                ),
            )
        recomputed = compute_event_hash(event)
        if recomputed != event.hash:
            return ChainVerification(
                ok=False,
                length=count,
                first_break_index=i,
                reason=(
                    f"hash mismatch at index {i}: stored {event.hash[:12]}… "
                    f"!= recomputed {recomputed[:12]}… (record was mutated)"
                ),
            )
        prev_hash = event.hash
    return ChainVerification(ok=True, length=count)
