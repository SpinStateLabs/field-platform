"""Caller-supplied correlation ids and notes, made safe for a ledger row.

A caller of the sentinel (``POST /check`` ``context``) or the governor
(``POST /usage`` / ``/spend`` ``note``) can say WHO it is acting for — e.g.
the claude-approver sends ``context.source = "claude-approver"`` and
``context.console_session_id = "sesn_..."``, and a usage ``note`` of
``"console session sesn_..."``. Putting those on the ledger lets an operator
correlate a Claude Console session with its ledger rows by id instead of by
time window (P30 item 5).

The input is caller-supplied and unauthenticated text, so only a fixed
allow-list of correlation keys is copied, only string values, whitespace
collapsed and truncated. Nothing here changes a decision: it is visibility
only. The values are LABELS a caller chose, not verified identities.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: The only ``context`` keys that reach the ledger. Ids and a source label;
#: everything else a caller sends stays out (it may be large or sensitive).
CORRELATION_KEYS: tuple[str, ...] = (
    "source",
    "session_id",
    "console_session_id",
    "console_agent_id",
    "session_thread_id",
    "event_id",
)

#: Per-value cap for a correlation id (Console ids are ~30 characters).
MAX_ID_CHARS = 200
#: Cap for a free-text note (the sentinel already truncates untrusted text
#: to 300 characters before it reaches the ledger).
MAX_NOTE_CHARS = 300


def _clean(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit]


def correlation_context(context: Mapping[str, Any] | None) -> dict[str, str]:
    """The allow-listed correlation keys of ``context`` whose values are
    non-empty strings, cleaned. Missing, non-string and empty values are
    dropped; an empty result means "nothing to ledger"."""
    if not isinstance(context, Mapping):
        return {}
    out: dict[str, str] = {}
    for key in CORRELATION_KEYS:
        value = context.get(key)
        if isinstance(value, str):
            cleaned = _clean(value, MAX_ID_CHARS)
            if cleaned:
                out[key] = cleaned
    return out


def ledger_note(note: str | None) -> str | None:
    """A caller's free-text note, cleaned for the ledger; None when absent or
    blank."""
    if not isinstance(note, str):
        return None
    cleaned = _clean(note, MAX_NOTE_CHARS)
    return cleaned or None
