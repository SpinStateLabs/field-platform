"""The board pack's period window (C4).

A window is what the ledger-derived counts are counted over. It is resolved
ONCE, before any service is queried, and every ``/events`` query in the pack
carries its bounds — so a pack can never label all-time counts as a quarter.

- ``parse_period("2026-Q3" | "Q3 2026")`` → the UTC calendar quarter
  ``[since, until]``, ``until`` = the quarter's last day 23:59:59.999999.
  Anything else is refused (``InvalidWindow``): a free-form caption is not a
  window, and neither is a non-ASCII digit or a year outside 0001..9999.
- ``normalise_bound`` turns each inclusive bound into a UTC instant: ``Z``
  is ``+00:00`` and a naive timestamp is UTC, as the ledger's ``parse_instant``
  (sealed-ledger ``filters.py``) reads them; a date alone expands to the start
  (``since``) or END (``until``) of that UTC day — unlike the ledger, which
  reads a raw date as the start of the day for both bounds. The pack only ever
  sends the normalised instants. A bound whose UTC instant is not a
  representable datetime (e.g. ``0001-01-01T00:00:00+01:00``) is refused.
- ``--period`` and ``--since``/``--until`` are mutually exclusive; neither ⇒
  ``kind='all-time'`` (no bounds on any query). A ``since`` without ``until``
  is closed at the generation instant, so the printed queries reproduce the
  counts later; an ``until`` without ``since`` has an open start.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, time, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict

# re.ASCII: \d is [0-9] only — "٢٠٢٦-Q3" is not a period.
_QUARTER = (re.compile(r"(?P<year>\d{4})-Q(?P<q>[1-4])", re.ASCII),
            re.compile(r"Q(?P<q>[1-4]) (?P<year>\d{4})", re.ASCII))


class InvalidWindow(ValueError):
    """A period or bound that is not a window (CLI exit 2, API 422)."""


class Window(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["quarter", "range", "all-time"]
    since: str | None = None  # ISO 8601 UTC, inclusive; None = open start
    until: str | None = None  # ISO 8601 UTC, inclusive; None only for all-time
    note: str

    def params(self) -> dict[str, str]:
        """The bounds as ledger query parameters — empty for all-time."""
        return {k: v for k, v in (("since", self.since), ("until", self.until)) if v is not None}


def parse_period(text: str) -> tuple[datetime, datetime]:
    """``"2026-Q3"`` or ``"Q3 2026"`` → (first instant, last microsecond) of
    that UTC calendar quarter. Strict: nothing else parses."""
    value = (text or "").strip()
    for pattern in _QUARTER:
        match = pattern.fullmatch(value)
        if match:
            year, q = int(match["year"]), int(match["q"])
            try:
                since = datetime(year, 3 * (q - 1) + 1, 1, tzinfo=timezone.utc)
                # the last day of the quarter's last month, not next-quarter - 1 µs:
                # 9999-Q4 has no next quarter
                last = date(year, 3 * q, calendar.monthrange(year, 3 * q)[1])
            except ValueError as exc:  # year 0000
                raise InvalidWindow(f"period {text!r} is outside years 0001..9999") from exc
            return since, datetime.combine(last, time.max, tzinfo=timezone.utc)
    raise InvalidWindow(
        f"period must be 'YYYY-Qn' or 'Qn YYYY' (e.g. '2026-Q3'), got {text!r}; "
        "use since/until for any other window"
    )


def normalise_bound(name: str, value: str, *, end: bool) -> datetime:
    """One inclusive bound → an aware UTC datetime. A date alone is the start
    of that day for ``since`` and its last microsecond for ``until``."""
    text = (value or "").strip()
    try:
        day = date.fromisoformat(text)
    except ValueError:
        day = None
    if day is not None:
        return datetime.combine(day, time.max if end else time.min, tzinfo=timezone.utc)
    if text[-1:] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise InvalidWindow(f"{name} is not an ISO 8601 date or timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        return parsed.astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:  # the UTC instant falls outside 0001..9999
        raise InvalidWindow(f"{name} {value!r} has no UTC instant between years 0001 and 9999") from exc


def resolve_window(
    period: str | None = None,
    since: str | None = None,
    until: str | None = None,
    *,
    now: datetime,
) -> tuple[Window, str]:
    """(window, period label). ``period`` and ``since``/``until`` are mutually
    exclusive; blank strings count as given (a blank is never all-time)."""
    if period is not None and (since is not None or until is not None):
        raise InvalidWindow("period and since/until are mutually exclusive — give one or the other")
    if period is not None:
        start, stop = parse_period(period)
        return Window(
            kind="quarter", since=start.isoformat(), until=stop.isoformat(),
            note="UTC calendar quarter; both bounds inclusive",
        ), period.strip()
    if since is None and until is None:
        return Window(
            kind="all-time",
            note="no window: every event in the LIVE ledger at generation",
        ), f"all-time, as of {now.date().isoformat()}"
    start = normalise_bound("since", since, end=False) if since is not None else None
    stop = normalise_bound("until", until, end=True) if until is not None else None
    notes = ["UTC; both bounds inclusive"]
    if stop is None:
        stop = now.astimezone(timezone.utc)
        notes.append("until = generation time (no until given)")
    if start is None:
        notes.append("open start (no since given)")
    if start is not None and start > stop:
        raise InvalidWindow(f"since {start.isoformat()} is after until {stop.isoformat()}")
    window = Window(
        kind="range", since=start.isoformat() if start else None,
        until=stop.isoformat(), note="; ".join(notes),
    )
    return window, f"{window.since or '…'} .. {window.until}"
