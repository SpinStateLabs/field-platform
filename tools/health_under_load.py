#!/usr/bin/env python3
"""health_under_load - T6 harness: does one heavy request make the estate's /health answers fail?

LOCAL ONLY. It refuses any base URL whose host is not loopback: ``seed`` writes thousands of ledger rows, and
neither command is meant for a live estate. Run it against the Fly image (``integration/fly/Dockerfile``) or the
compose stack on your own machine.

    python tools/health_under_load.py seed --base http://127.0.0.1:8080 --events 11200
    python tools/health_under_load.py run  --base http://127.0.0.1:8080 --heavy /attest/pack \
        [--prefixes registry,ledger,...] [--pre 10] [--post 4] [--container estate] [--json out.json]

``seed`` appends N events through ``POST /ledger/events`` (the ledger's own append path, so the hash chain is the
ledger's; about 650 bytes per stored row, eight event types, forty agent ids). ``run`` polls every prefix's
``/health`` once a second with a 5 s timeout, one thread per prefix (one slow service never delays another's poll),
for ``--pre`` seconds, then issues ONE heavy GET and keeps polling until ``--post`` seconds after it returns. A poll
counts as failed when it is not a 200 or took 5 s or more (the estate monitor's rule; two in a row roll back).
``--container`` also prints each process's CPU time spent during the heavy request (``docker exec`` reading
``/proc/<pid>/stat``), which names the process doing the work.

The shared secret, when the stack has one, is read from ``$FIELD_SHARED_SECRET`` and sent as ``x-field-auth``;
use a test value. It is never printed. Standard library only; the opener ignores the proxy environment (C-57).
Exit status: 0 done (the table is the result, not a verdict), 2 usage error or a refused base URL.
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

#: every proxy prefix of the Fly image's Caddyfile; "console" is the bare /health (the console owns the root)
PREFIXES = ("registry", "ledger", "delegation", "sentinel", "killswitch", "governor", "replay", "gateway",
            "federation", "lifecycle", "attest", "crosswalk", "console")
HEALTH_TIMEOUT = 5.0
LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
EVENT_TYPES = ("gateway.request", "conformance.allow", "conformance.block", "delegation.mint",
               "governor.spend", "lifecycle.reattestation_due", "kill.agent", "gateway.refused")
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
# /proc/<pid>/stat utime+stime (clock ticks) of every `<name> serve|run` process in the container
_CPU_SNAPSHOT = r"""for p in /proc/[0-9]*; do [ -r $p/stat ] || continue
n=$(tr "\0" " " < $p/cmdline 2>/dev/null | awk '{for(i=1;i<=NF;i++) if ($i=="serve"||$i=="run") {print $(i-1); exit}}')
[ -n "$n" ] && awk -v n="$n" '{print n, $14+$15}' $p/stat; done; getconf CLK_TCK"""


def loopback_base(base: str) -> str:
    """The base URL without a trailing slash, or SystemExit(2) when its host is not loopback."""
    parts = urllib.parse.urlsplit(base)
    if parts.scheme not in ("http", "https") or parts.hostname not in LOOPBACK:
        raise SystemExit(f"refused: {base!r} is not a loopback http(s) URL - this harness is for a local stack only")
    return base.rstrip("/")


def health_url(base: str, prefix: str) -> str:
    return f"{base}/health" if prefix == "console" else f"{base}/{prefix}/health"


def request(method: str, url: str, body: dict | None = None, timeout: float = HEALTH_TIMEOUT
            ) -> tuple[int | str, float, int]:
    """(HTTP status or exception name, seconds, response bytes)."""
    req = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(), method=method)
    req.add_header("content-type", "application/json")
    secret = os.environ.get("FIELD_SHARED_SECRET", "")
    if secret:
        req.add_header("x-field-auth", secret)
    t0 = time.monotonic()
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return resp.status, time.monotonic() - t0, len(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, time.monotonic() - t0, 0
    except Exception as exc:  # noqa: BLE001 - a timeout or a reset is a failed poll, by name
        return type(exc).__name__, time.monotonic() - t0, 0


def seed(base: str, n: int, workers: int = 4) -> float:
    pad = "x" * 260

    def one(i: int) -> None:
        body = {"event_type": EVENT_TYPES[i % len(EVENT_TYPES)], "agent_id": f"t6-agent-{i % 40:03d}",
                "payload": {"seq": i, "token_id": f"t6-tok-{i % 300:04d}", "model": "claude-x",
                            "cost_cents": i % 97, "note": pad}}
        status: int | str = 0
        for _ in range(5):
            status, _, _ = request("POST", f"{base}/ledger/events", body, timeout=30)
            if status == 201:
                return
            time.sleep(0.2)
        raise RuntimeError(f"append {i} answered {status}")

    t0 = time.monotonic()
    with ThreadPoolExecutor(workers) as pool:
        list(pool.map(one, range(n)))
    return time.monotonic() - t0


def failed(status: int | str, seconds: float) -> bool:
    return status != 200 or seconds >= HEALTH_TIMEOUT


def summarize(polls: list[tuple[float, int | str, float]], start: float, end: float) -> dict:
    """One prefix: idle max before ``start``; count, failures, longest failing run, p50, max inside [start, end]."""
    before = [dt for t, _, dt in polls if t < start]
    during = [(s, dt) for t, s, dt in polls if start <= t <= end]
    streak = longest = 0
    for s, dt in during:
        streak = streak + 1 if failed(s, dt) else 0
        longest = max(longest, streak)
    lat = [dt for _, dt in during]
    return {"idle_max": round(max(before), 3) if before else None, "n": len(during),
            "failed": sum(1 for s, dt in during if failed(s, dt)), "max_consecutive_failed": longest,
            "p50": round(statistics.median(lat), 3) if lat else None, "max": round(max(lat), 3) if lat else None}


def cpu_ticks(container: str) -> tuple[dict[str, int], int]:
    out = subprocess.run(["docker", "exec", container, "sh", "-c", _CPU_SNAPSHOT], capture_output=True,
                         text=True, timeout=60, check=True).stdout.split("\n")
    lines = [ln for ln in out if ln.strip()]
    ticks: dict[str, int] = {}
    for ln in lines[:-1]:
        name, value = ln.rsplit(" ", 1)
        name = name.rsplit("/", 1)[-1]
        ticks[name] = ticks.get(name, 0) + int(value)
    return ticks, int(lines[-1])


def run(base: str, heavy: str, prefixes: list[str], pre: float, post: float, container: str | None) -> dict:
    stop = threading.Event()
    polls: dict[str, list] = {p: [] for p in prefixes}

    def poll(prefix: str) -> None:
        url = health_url(base, prefix)
        while not stop.is_set():
            t = time.monotonic()
            status, dt, _ = request("GET", url)
            polls[prefix].append((t, status, dt))
            stop.wait(max(0.0, 1.0 - (time.monotonic() - t)))

    threads = [threading.Thread(target=poll, args=(p,), daemon=True) for p in prefixes]
    for th in threads:
        th.start()
    time.sleep(pre)
    cpu0 = cpu_ticks(container) if container else None
    start = time.monotonic()
    status, seconds, size = request("GET", f"{base}{heavy}", timeout=900)
    end = time.monotonic()
    cpu1 = cpu_ticks(container) if container else None
    time.sleep(post)
    stop.set()
    for th in threads:
        th.join(timeout=HEALTH_TIMEOUT + 2)
    result = {"heavy": heavy, "status": status, "seconds": round(seconds, 2), "bytes": size,
              "health": {p: summarize(polls[p], start, end) for p in prefixes}}
    if cpu0 and cpu1:
        hz = cpu1[1]
        result["cpu_ms"] = {k: round((v - cpu0[0].get(k, 0)) * 1000 / hz)
                            for k, v in sorted(cpu1[0].items()) if v - cpu0[0].get(k, 0) > 0}
    return result


def table(res: dict) -> str:
    rows = [f"heavy GET {res['heavy']} -> {res['status']} in {res['seconds']} s ({res['bytes']} B)",
            "| /health of | idle max s | polls during | failed | max consecutive failed | p50 s | max s |",
            "|---|---|---|---|---|---|---|"]
    for name, v in res["health"].items():
        rows.append(f"| {name} | {v['idle_max']} | {v['n']} | {v['failed']} | {v['max_consecutive_failed']} "
                    f"| {v['p50']} | {v['max']} |")
    if "cpu_ms" in res:
        rows.append("CPU during the heavy request (ms): "
                    + ", ".join(f"{k} {v}" for k, v in res["cpu_ms"].items()))
    return "\n".join(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("seed", help="append N events through POST /ledger/events")
    s.add_argument("--base", required=True)
    s.add_argument("--events", type=int, default=11200)
    r = sub.add_parser("run", help="poll every /health around one heavy GET")
    r.add_argument("--base", required=True)
    r.add_argument("--heavy", required=True, help="path, e.g. /attest/pack, /ledger/verify, /ledger/events")
    r.add_argument("--prefixes", default=",".join(PREFIXES))
    r.add_argument("--pre", type=float, default=10.0)
    r.add_argument("--post", type=float, default=4.0)
    r.add_argument("--container", help="docker container name: also report per-process CPU during the request")
    r.add_argument("--json", help="also write the result as JSON to this file")
    args = ap.parse_args(argv)
    base = loopback_base(args.base)
    if args.cmd == "seed":
        print(f"seeded {args.events} events in {seed(base, args.events):.1f} s")
        return 0
    prefixes = [p for p in args.prefixes.split(",") if p]
    unknown = sorted(set(prefixes) - set(PREFIXES))
    if unknown or not args.heavy.startswith("/"):
        print(f"usage: unknown prefixes {unknown} or --heavy not a path", file=sys.stderr)
        return 2
    res = run(base, args.heavy, prefixes, args.pre, args.post, args.container)
    print(table(res))
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
