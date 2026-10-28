#!/usr/bin/env python3
"""Key rotation slice R2: does the edge proxy refuse the two internal routes?

    [FIELD_SHARED_SECRET=...] python3 check_edge_block.py <proxy-base-url> [--cacert PATH]

Standard library only (it runs on the bare CI runner). Run by compose-smoke
(base Caddyfile on 8080), compose-upgrade-smoke (GB10 Caddyfile.gb10: 18080
and the TLS listener 18443) and fly-image-smoke (integration/fly/Caddyfile):
from the runner, which is NEVER the proxy's loopback, every request for
``/operator/verify-hash`` or ``/operator/rotation-state`` under every
operator-block service prefix (and the console root) must be answered by Caddy
itself: 403 with the body ``internal route: loopback only``. The perimeter
secret is sent when the estate has one (from the environment, never argv,
never printed), so a 403 here cannot be the services' own 401. Case and
percent-encoding variants and a spoofed X-Forwarded-For are tried too.

That the routes still reach the services from the proxy's own loopback is the
CI step's second half (a request from inside the proxy container must get the
service's answer, never Caddy's 403).

Exit 0 every request refused at the edge, 1 any request got through or
another answer, 2 usage."""

from __future__ import annotations

import argparse
import os
import ssl
import sys
import urllib.error
import urllib.request

PREFIXES = ("registry", "ledger", "delegation", "killswitch", "governor", "federation",
            "lifecycle", "")
ROUTES = (("POST", "operator/verify-hash"), ("GET", "operator/rotation-state"))
EDGE_BODY = "internal route: loopback only"
BODY = b'{"operator_id":"svc-killswitch","key_sha256":"' + b"0" * 64 + b'"}'


def _variants(prefix: str, route: str) -> list[str]:
    base = f"/{prefix}/{route}" if prefix else f"/{route}"
    return [base, base + "/", base.upper(), base.replace("verify-hash", "verify%2Dhash")
            .replace("rotation-state", "rotation%2Dstate"), base + "?x=1"]


def _ask(url: str, method: str, secret: str | None, ctx, spoof: bool) -> tuple[int, str]:
    headers = {"content-type": "application/json"}
    if secret:
        headers["x-field-auth"] = secret
    if spoof:
        headers["x-forwarded-for"] = "127.0.0.1"
    req = urllib.request.Request(url, data=BODY if method == "POST" else None,
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            return resp.status, resp.read(4096).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(4096).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as exc:
        return 0, type(exc).__name__


def check(base: str, cacert: str | None) -> list[str]:
    secret = os.environ.get("FIELD_SHARED_SECRET") or None
    ctx = ssl.create_default_context(cafile=cacert) if base.startswith("https://") else None
    problems = []
    n = 0
    for prefix in PREFIXES:
        for method, route in ROUTES:
            for i, path in enumerate(_variants(prefix, route)):
                for spoof in ((False, True) if i == 0 else (False,)):
                    n += 1
                    status, body = _ask(base.rstrip("/") + path, method, secret, ctx, spoof)
                    if status != 403 or body.strip() != EDGE_BODY:
                        problems.append(f"{method} {path}{' (spoofed XFF)' if spoof else ''}: "
                                        f"{status} {body[:80]!r}")
    print(f"{n} requests to the internal routes through {base}: "
          f"{n - len(problems)} refused at the edge")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("base")
    ap.add_argument("--cacert")
    try:
        args = ap.parse_args(argv)
    except SystemExit:
        return 2
    problems = check(args.base, args.cacert)
    for p in problems:
        print(f"::error::not refused at the edge: {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
