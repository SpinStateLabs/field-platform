#!/usr/bin/env python3
"""stage1_window - the Stage 1 clean-window evaluation of Phase G, made mechanical (G18).

    python tools/stage1_window.py snapshot --base URL --out FILE
    python tools/stage1_window.py evaluate --before FILE --after FILE [--records PATH [--build-sha SHA]] [--min-hours H]

The Stage 1 window is clean when, between two reads of the services' ``/health``, ``dropped_unauthenticated_records`` and
``dropped_refused_records`` did not rise on any service. ``tools/stage_controller.py`` already judges that between the
steps of a run (``_increases``, the G24 abort rule); what it does not do is judge a whole window from two saved reads
and leave a record that Stage 2 can look for. This module fills only that gap and reuses the controller's own rule, so
there is one definition of "an increase".

* ``snapshot`` reads ``GET /<prefix>/health`` (no credential) of the eight operator-block services and writes
  ``{"taken_at": <epoch seconds>, "counters": {service: {counter: int}}}``. A counter that is missing or not an
  integer is written as null: it cannot be judged, which fails the window.
* ``evaluate`` compares two snapshots with the controller's rule. It FAILS CLOSED: an empty ``before``, a service in
  ``before`` that is absent from ``after``, a missing or non-integer counter, a window that does not run forward in
  time, one shorter than ``--min-hours`` (default 24) or a service label of the eight absent from either snapshot, a non-finite `taken_at` (NaN, Infinity) or `--min-hours`, a window ending in the future, a counter that went DOWN (the counters live in the process, so
  a decrease is a restart and the window cannot be judged) is not clean. Equal counters over a long enough window pass.
  With ``--records`` a PASS appends one ``gate G18`` row (bound to ``--build-sha`` when given, and carrying
  ``window_hours``, ``window_end`` and ``services`` so the row shows what was judged) and a failure writes nothing.
  The snapshot files are local JSON that nothing signs (the controller's records file has the same trust model).

It prints service labels, counter names and verdict words only; no value other than the verdict is echoed from /health.
It never arms, never mutates an estate and holds no key. Exit status: 0 clean window, 1 not clean, 2 usage error.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import estate_probe as ep  # noqa: E402
import stage_controller as sc  # noqa: E402

# One definition: the stage 0 check owns the table; this module reuses it so the two cannot drift.
from phase_g_stage0_check import OPERATOR_BLOCK_SERVICES  # noqa: E402

GATE = "G18"
SECONDS_PER_HOUR = 3600.0
#: The shortest window that counts as a Stage 1 window (the runbook's Stage 2 entry states it). A shorter one, or one
#: where the flag was forgotten, is not clean: the default is not zero.
DEFAULT_MIN_HOURS = 24.0


def _finite(value: Any) -> bool:
    """A real, finite number. `math.isfinite` raises OverflowError for an integer too large for a float (10**400), which is
    also not a usable time or length: that is False here, never an exception (R-PR837 a6e2ec3 C1)."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def read_snapshot(estate: Any, now: float | None = None) -> dict:
    counters: dict[str, dict[str, int | None]] = {}
    for label, path, service in OPERATOR_BLOCK_SERVICES:
        status, body = estate.call("GET", path, auth=False)
        ok = status == 200 and isinstance(body, dict) and body.get("service") == service
        counters[label] = {key: (_int(body.get(key)) if ok else None) for key in sc.COUNTER_KEYS}
    return {"taken_at": time.time() if now is None else now, "counters": counters}


#: How far past "now" a snapshot's own clock may run before the window is refused (clock skew between the host that took
#: the snapshot and the host that judges it).
FUTURE_SKEW_SECONDS = 300.0
#: The label every snapshot must hold, one per operator-block service (R-PR837 C1).
REQUIRED_LABELS = tuple(label for label, _path, _service in OPERATOR_BLOCK_SERVICES)


def evaluate_window(before: Any, after: Any, min_hours: float = DEFAULT_MIN_HOURS, now: float | None = None) -> list[str]:
    """Problems that make the window not clean (empty list = clean). Fixed words only. `now` (default: the clock) bounds
    the window end: an `after` snapshot dated in the future is not evidence about the present (R-PR837 C2)."""
    problems: list[str] = []
    if not (isinstance(before, dict) and isinstance(after, dict)):
        return ["a snapshot is not an object"]
    b, a = before.get("counters"), after.get("counters")
    if not isinstance(b, dict) or not b:
        return ["the before snapshot holds no counters"]
    if not isinstance(a, dict):
        return ["the after snapshot holds no counters"]
    t0, t1 = before.get("taken_at"), after.get("taken_at")
    if not _finite(min_hours):
        problems.append("the minimum window length is not a finite number")     # NaN passes every length comparison
    if not all(isinstance(t, (int, float)) and not isinstance(t, bool) for t in (t0, t1)):
        problems.append("the window does not run forward in time")
    elif not (_finite(t0) and _finite(t1)):
        # json.loads accepts NaN and Infinity, and NaN is false in every comparison below: a clean window by default
        problems.append("a snapshot's taken_at is not a finite number")
    elif t1 <= t0:
        problems.append("the window does not run forward in time")
    elif _finite(min_hours) and (t1 - t0) < min_hours * SECONDS_PER_HOUR:
        problems.append(f"the window is shorter than {min_hours:g} hour(s)")
    elif t1 > (time.time() if now is None else now) + FUTURE_SKEW_SECONDS:
        problems.append("the window ends in the future")
    for label in REQUIRED_LABELS:           # all eight services, in both snapshots: one service cannot stand for the estate
        for side, snap in (("before", b), ("after", a)):
            if label not in snap:
                problems.append(f"{label}: missing from the {side} snapshot")
    for abort in sorted(sc._increases(b, a), key=lambda x: x.value):
        problems.append(abort.value)
    for service in b:                       # a counter must be present on both sides, not merely not-increased
        for key in sc.COUNTER_KEYS:
            for side, snap in (("before", b), ("after", a)):
                cur = snap.get(service) if isinstance(snap.get(service), dict) else None
                if cur is None or _int(cur.get(key)) is None:
                    problems.append(f"{service}: {key} missing or not a number in the {side} snapshot")
    for service in b:                       # a counter that went DOWN is a restart (the counters live in the process)
        for key in sc.COUNTER_KEYS:
            lo, hi = (_int(b[service].get(key)), _int(a.get(service, {}).get(key))) if (
                isinstance(b.get(service), dict) and isinstance(a.get(service), dict)) else (None, None)
            if lo is not None and hi is not None and hi < lo:
                problems.append(f"{service}: {key} went down: the service restarted, the window cannot be judged")
    return list(dict.fromkeys(problems))


def _load(path: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="stage1_window", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    snap = sub.add_parser("snapshot", help="read the dropped-record counters of the eight services from /health")
    snap.add_argument("--base", required=True)
    snap.add_argument("--out", required=True)
    ev = sub.add_parser("evaluate", help="judge the window between two snapshots (fails closed)")
    ev.add_argument("--before", required=True)
    ev.add_argument("--after", required=True)
    ev.add_argument("--min-hours", type=float, default=DEFAULT_MIN_HOURS,
                    help=f"shortest window that counts (default {DEFAULT_MIN_HOURS:g})")
    ev.add_argument("--records", help="append a gate G18 row to this controller records file on a clean window")
    ev.add_argument("--build-sha", dest="build_sha")
    args = ap.parse_args(argv)
    if args.cmd == "snapshot":
        data = read_snapshot(ep.Estate(args.base, None))
        Path(args.out).write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
        missing = [f"{s}:{k}" for s, c in data["counters"].items() for k, v in c.items() if v is None]
        print(f"snapshot of {len(data['counters'])} services written; {len(missing)} counter(s) not readable"
              + (f" ({', '.join(missing)})" if missing else ""))
        return 0
    if not _finite(args.min_hours) or args.min_hours < 0 or (args.build_sha and not args.records):
        print("error: --min-hours must be a finite number, not negative, and --build-sha needs --records")
        return 2
    before, after = _load(args.before), _load(args.after)
    if before is None or after is None:
        print("error: a snapshot file cannot be read")
        return 2
    problems = evaluate_window(before, after, args.min_hours)
    if problems:
        print("[FAIL] the Stage 1 window is NOT clean:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("[PASS] the Stage 1 window is clean: no dropped-record counter rose on any service")
    if args.records:
        try:
            sha = {"sha8": sc.sha8_of(args.build_sha)} if args.build_sha else {}
        except sc.Refused as exc:
            print(f"refused: {exc.reason}")
            return 2
        span = {"window_hours": round((after["taken_at"] - before["taken_at"]) / SECONDS_PER_HOUR, 2),
                "window_end": int(after["taken_at"]),               # when the window closed: Stage 2 judges how old it is
                "services": len(before["counters"])}
        sc.Records(args.records).append("gate", gate=GATE, ok=True, **sha, **span)
        print(f"recorded gate {GATE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
