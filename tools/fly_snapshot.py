#!/usr/bin/env python3
"""fly_snapshot.py - accept only a COMPLETED Fly volume snapshot with a real created_at (B-GL-snapshot-status-values).

Why. The cb7a94f deploy script's P0S gate accepted a snapshot whose status was "waiting" and whose created_at was
0001-01-01 (a deny-list of three bad statuses and a date-shape regex). A snapshot that is still being taken is not a
rollback point. This module is the allow-list: ONE status completes a snapshot, and the date must be a real one.

What Fly documents and what is only observed (docs read 2026-11-21; docs.fly.io, the old fly.io/docs URLs redirect there):

DOCUMENTED
- https://docs.fly.io/volumes/snapshots : "The state of the new snapshot will go from `waiting` to `running` to
  `created`." and the `fly volumes snapshots list` example table has the columns "ID STATUS STORED SIZE VOL SIZE
  CREATED AT RETENTION DAYS" with the rows `... created 2.0 GiB 10 GiB 5 days ago 5` and `... running 0 B 10 GiB`
  (the running row has an EMPTY created_at and retention). So documented values: `created` (finished), `running`
  and `waiting` (in progress). No other snapshot status is named on THESE TWO pages (the volumes-resource page names the volume states
  `created`, `restoring`, `destroyed`, which are not snapshot statuses): not "pending", "creating", "complete",
  "failed". The flyctl source and the OpenAPI spec could not be read, so other values may exist.
- https://docs.fly.io/machines/api/volumes-resource : the Machines API snapshot LIST example has the fields id, size,
  digest, created_at, retention_days and NO status field; created_at is written like "2023-12-02T20:59:35+00:00". The
  on-demand create example returns a backup object whose state is "prepare" (the field is `state`, not `status`) with a
  created_at "2024-02-16T19:30:43.914350121Z" already filled while the backup is not finished. So a populated
  created_at does not prove completion: only the status does.
- No page gives an enum for the status and the OpenAPI spec could not be fetched (docs.machines.dev/spec/openapi3.json
  redirects to a 404), so the list of in-progress or failed values is NOT exhaustive.

OBSERVED (not documented)
- The estate audit (2026-11-21) saw a snapshot with `status=waiting`, `created_at=0001-01-01T00:00:00Z`, `size=0`
  pass the P0S gate. The zero time is not described in the docs; this module refuses it by range (year < 2020), not by
  naming it.
- The `--json` output of `fly volumes snapshots list` carries a `status` key (the docs only show it in the table);
  the deploy script reads it that way. If a response has no `status` key, `state` is read instead (the backup object).

Rule (fail closed): the status must be exactly `created` (case and surrounding spaces ignored); any other value,
including every documented in-progress value and every unknown one, is refused, with a different reason so a caller
can tell "still running, wait" from "not understood, stop". created_at must be an ISO 8601 date-time WITH an offset
or Z (fractional seconds of any length), in the year 2020 or later and not more than five minutes in the future.
Optionally the snapshot must be no older than ``max_age``.

CLI (stdlib only, no network, never calls fly):
    fly volumes snapshots list VOL -a APP --json | python tools/fly_snapshot.py check --id vs_xxx [--max-age-hours 2]
exit 0 = completed (prints one OK line), 1 = refused (prints one REFUSED line with the reason), 2 = usage or unreadable input.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from typing import Any, NamedTuple

COMPLETE_STATUS = "created"                 # documented: the end of waiting -> running -> created
IN_PROGRESS_STATUSES = ("waiting", "running")  # documented as the states before it
MIN_YEAR = 2020                             # Fly Machines volumes snapshots did not exist before this
FUTURE_SKEW = dt.timedelta(minutes=5)

_ISO = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?(Z|[+-]\d{2}:\d{2})$", re.ASCII)


class Verdict(NamedTuple):
    ok: bool
    code: str      # "ok", "in-progress", "bad-status", "bad-created-at", "too-old", "not-a-snapshot"
    reason: str


def parse_created_at(value: Any) -> dt.datetime | None:
    """A timezone-aware datetime for an ISO 8601 string with an offset or Z, else None. Fractional seconds of
    any length are accepted (Fly writes nanoseconds); an impossible date is None, never an exception."""
    if not isinstance(value, str):
        return None
    m = _ISO.match(value.strip())
    if not m:
        return None
    year, month, day, hour, minute, sec, frac, zone = m.groups()
    try:
        if zone != "Z" and int(zone[4:6]) > 59:
            return None
        micro = int((frac or "0")[:6].ljust(6, "0"))
        tz = dt.timezone.utc if zone == "Z" else dt.timezone(
            (1 if zone[0] == "+" else -1) * dt.timedelta(hours=int(zone[1:3]), minutes=int(zone[4:6])))
        return dt.datetime(int(year), int(month), int(day), int(hour), int(minute), int(sec), micro, tzinfo=tz)
    except (ValueError, OverflowError):
        return None


def snapshot_complete(snap: Any, *, now: dt.datetime | None = None,
                      max_age: dt.timedelta | None = None) -> Verdict:
    """Accept only a completed snapshot with a real created_at (see the module docstring for the rule)."""
    if not isinstance(snap, dict):
        return Verdict(False, "not-a-snapshot", "the snapshot is not a JSON object")
    raw_status = snap["status"] if "status" in snap else snap.get("state")
    status = raw_status.strip().lower() if isinstance(raw_status, str) else None
    if status != COMPLETE_STATUS:
        if status in IN_PROGRESS_STATUSES:
            return Verdict(False, "in-progress",
                           f"status is {status!r}: the snapshot is still being taken (documented in-progress state)")
        return Verdict(False, "bad-status",
                       f"status {raw_status!r} is not {COMPLETE_STATUS!r} (not a documented completed state)")
    created = parse_created_at(snap.get("created_at"))
    if created is None:
        return Verdict(False, "bad-created-at", f"created_at {snap.get('created_at')!r} is not an ISO 8601 date-time with an offset")
    now = now or dt.datetime.now(dt.timezone.utc)
    if created.year < MIN_YEAR:
        return Verdict(False, "bad-created-at", f"created_at {snap.get('created_at')!r} is before {MIN_YEAR} (a zero or placeholder time)")
    if created > now + FUTURE_SKEW:
        return Verdict(False, "bad-created-at", f"created_at {snap.get('created_at')!r} is in the future")
    if max_age is not None and now - created > max_age:
        return Verdict(False, "too-old", f"created_at {snap.get('created_at')!r} is older than the {max_age} allowed")
    return Verdict(True, "ok", f"status {COMPLETE_STATUS!r}, created_at {snap.get('created_at')!r}")


def load_json(text: str) -> Any:
    """The first JSON array or object in ``text`` that parses (a flyctl run may print a line or two before it, and
    such a line may itself contain a bracket); anything after the value is ignored."""
    decoder = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "[{":
            try:
                value, _ = decoder.raw_decode(text, i)
            except ValueError:
                continue
            if isinstance(value, (list, dict)):
                return value
    raise ValueError("no JSON in the input")


def main(argv: list[str] | None = None, stdin: Any = None) -> int:
    ap = argparse.ArgumentParser(description="Accept only a completed Fly volume snapshot with a real created_at.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="read `fly volumes snapshots list --json` on stdin")
    c.add_argument("--id", help="the snapshot id to check (required when stdin is a list)")
    c.add_argument("--max-age-hours", type=float, help="refuse a snapshot older than this")
    c.add_argument("--now", help="ISO 8601 time to treat as now (tests)")
    args = ap.parse_args(argv)
    try:
        data = load_json((stdin or sys.stdin).read())
    except (ValueError, OSError) as exc:
        print(f"UNREADABLE: {type(exc).__name__}")
        return 2
    if isinstance(data, list):
        if not args.id:
            print("UNREADABLE: stdin is a list; pass --id")
            return 2
        picked = [s for s in data if isinstance(s, dict) and s.get("id") == args.id]
        if len(picked) != 1:
            print(f"REFUSED: snapshot id {args.id!r} appears {len(picked)} times in the list (want exactly 1)")
            return 1
        snap = picked[0]
    else:
        snap = data
        if args.id and isinstance(snap, dict) and snap.get("id") != args.id:
            print(f"REFUSED: the snapshot's id is not {args.id!r}")
            return 1
    now = parse_created_at(args.now) if args.now else None
    if args.now and now is None:
        print("UNREADABLE: --now is not an ISO 8601 date-time with an offset")
        return 2
    if args.max_age_hours is not None and not (0 < args.max_age_hours < 24 * 365 * 10):
        print("UNREADABLE: --max-age-hours must be a number above 0 and below ten years")
        return 2
    max_age = dt.timedelta(hours=args.max_age_hours) if args.max_age_hours is not None else None
    verdict = snapshot_complete(snap, now=now, max_age=max_age)
    print(("OK " if verdict.ok else "REFUSED: ") + f"{verdict.code}: {verdict.reason}")
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
