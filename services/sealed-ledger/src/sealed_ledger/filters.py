"""Event filters shared by ``GET /events``, the auditor export and
``ledger verify-export``.

ENFORCED: ``since``/``until`` compare INSTANTS, not strings. Bounds and event
timestamps are parsed with ``datetime.fromisoformat``, so ``...T10:00:00Z``,
``...T10:00:00+00:00`` and ``...T06:00:00-04:00`` are the same moment. Both
bounds are inclusive. A naive timestamp (no offset, or a date alone) is taken
as UTC; a date alone means 00:00:00 UTC on that day. A bound that does not
parse raises ``InvalidTimeBound`` (the API answers 422), never a silent empty
result.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from field_core.ledger import LedgerEvent


class InvalidTimeBound(ValueError):
    """A ``since``/``until`` value that is not an ISO 8601 timestamp."""


def parse_instant(value: str) -> datetime:
    """ISO 8601 text -> timezone-aware datetime (naive input is taken as UTC)."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_bound(name: str, value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return parse_instant(value)
    except (TypeError, ValueError) as exc:
        raise InvalidTimeBound(
            f"{name} is not an ISO 8601 timestamp: {value!r}"
        ) from exc


class EventFilter:
    """``agent_id`` / ``event_type`` exact match; ``since``/``until`` inclusive
    instants. Bounds are parsed once, at construction."""

    def __init__(
        self,
        agent_id: str | None = None,
        event_type: str | None = None,
        since: str | None = None,
        until: str | None = None,
    ):
        self.agent_id = agent_id
        self.event_type = event_type
        self.since = since
        self.until = until
        self._since = parse_bound("since", since)
        self._until = parse_bound("until", until)

    def as_dict(self) -> dict[str, Any]:
        return {
            "since": self.since,
            "until": self.until,
            "agent_id": self.agent_id,
            "event_type": self.event_type,
        }

    def matches(self, index: int, event: LedgerEvent) -> bool:
        if self.agent_id is not None and event.agent_id != self.agent_id:
            return False
        if self.event_type is not None and event.event_type != self.event_type:
            return False
        if self._since is None and self._until is None:
            return True
        try:
            ts = parse_instant(event.ts)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"event at index {index} has a ts that is not ISO 8601: {event.ts!r}"
            ) from exc
        if self._since is not None and ts < self._since:
            return False
        if self._until is not None and ts > self._until:
            return False
        return True
