#!/usr/bin/env python3
"""Phase G C-6: has the ledger's operator observer ledgered every operator-block service?

    [FIELD_SHARED_SECRET=...] python3 check_rows.py <ledger-base-url> [--wait SECONDS] [--mode MODE]

Standard library only (it runs on the bare CI runner, through the proxy). Run
by compose-smoke, compose-upgrade-smoke and fly-image-smoke on the real
containers. It polls ``GET <ledger>/events?event_type=...`` until every one of
the eight services that report an operator block (the ledger itself and the
seven in FIELD_LEDGER_OBSERVE_HEALTH) has an ``operator.mode_changed`` AND an
``operator.registry_changed`` row, then checks each service's FIRST row of each
type: ``startup: true``, ``observed_from: "health"``, ``previous_mode`` null and
the expected mode (default ``off``: no operator flag is set in CI). The wait
covers the observer's second tick: a service that was not yet answering at the
ledger's start-up tick is recorded on the next one (60 s later on the estates).

The perimeter secret, when the estate has one, comes from the environment
(FIELD_SHARED_SECRET), never from argv, and is never printed.
Exit 0 all present and correct, 1 missing or wrong, 2 refused (usage)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

#: the flag-bearing eight, by the names the observer records (``service``)
SERVICES = ("sealed-ledger", "agent-registry", "delegation-authority", "kill-switch", "spend-governor",
            "federation-broker", "ops-console", "lifecycle-manager")
MODE_EVENT = "operator.mode_changed"
REGISTRY_EVENT = "operator.registry_changed"


def _events(base: str, event_type: str, secret: str | None) -> list[dict]:
    headers = {"Accept": "application/json"}
    if secret:
        headers["x-field-auth"] = secret
    req = urllib.request.Request(f"{base}/events?event_type={event_type}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _first_by_service(events: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for e in events:
        p = e.get("payload") if isinstance(e, dict) else None
        if isinstance(p, dict) and isinstance(p.get("service"), str):
            out.setdefault(p["service"], p)
    return out


def check(base: str, wait: float, mode: str, secret: str | None) -> list[str]:
    deadline = time.monotonic() + wait
    while True:
        modes = _first_by_service(_events(base, MODE_EVENT, secret))
        regs = _first_by_service(_events(base, REGISTRY_EVENT, secret))
        missing = [f"{s} ({t})" for s in SERVICES for t, got in ((MODE_EVENT, modes), (REGISTRY_EVENT, regs))
                   if s not in got]
        if not missing or time.monotonic() > deadline:
            break
        time.sleep(2)
    problems = [f"no {m} row" for m in missing]
    for s, p in modes.items():
        if s in SERVICES and (p.get("mode"), p.get("previous_mode"), p.get("startup"),
                              p.get("observed_from")) != (mode, None, True, "health"):
            problems.append(f"{s}: first {MODE_EVENT} is {p}")
    for s, p in regs.items():
        if s in SERVICES and (p.get("startup"), p.get("observed_from")) != (True, "health"):
            problems.append(f"{s}: first {REGISTRY_EVENT} is {p}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("ledger", help="ledger base URL, e.g. http://localhost:8080/ledger")
    ap.add_argument("--wait", type=float, default=150.0, help="seconds to wait for the rows (default 150)")
    ap.add_argument("--mode", default="off", choices=("off", "log-only", "enforce"))
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2
    if not args.ledger.startswith(("http://", "https://")):
        print("refused: the ledger base must be http(s)://...", file=sys.stderr)
        return 2
    problems = check(args.ledger.rstrip("/"), args.wait, args.mode, os.environ.get("FIELD_SHARED_SECRET") or None)
    for p in problems:
        print(f"FAIL C-6 observer: {p}")
    if problems:
        return 1
    print(f"PASS C-6 observer: {len(SERVICES)}/{len(SERVICES)} services have startup "
          f"{MODE_EVENT} (mode {args.mode}) and {REGISTRY_EVENT} rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
