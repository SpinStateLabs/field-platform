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
never printed), so a 403 here cannot be the services' own 401. Twenty-four path
shapes per route are tried (case, percent-encoding, doubled and dot segments,
``;x=1``, NUL, space, ahead of the prefix, lower-case ``%2f``, trailing dot; the
C-27 real-Caddy probe classes) and a spoofed X-Forwarded-For on the plain path.
Two more shapes (double encoding ``%252F`` and a backslash) are sent and reported
as ``info:`` lines: the real proxy passes them to the service's own 404, so they
fail the check only on a 2xx answer. Not probed at all: other methods, other
encodings of the host.

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
    last = route.split("/")[1]
    seam = "/operator/"
    return [base, base + "/", base.upper(), base.replace("verify-hash", "verify%2Dhash")
            .replace("rotation-state", "rotation%2Dstate"), base + "?x=1",
            # the shapes of the C-27 real-Caddy probe (C-32): doubled and encoded slashes, dot
            # segments, a parameter, NUL, space, mixed case; each must still be refused at the edge
            base.replace(seam, "//operator/"), base.replace(seam, "/operator//"),
            base.replace(seam, "/%6fperator/"), base.replace(seam, "/operator%2F"),
            base.replace(seam, "/%2Foperator/"), base.replace(seam, "/./operator/"),
            base.replace(seam, "/operator/./"), base.replace(seam, "/x/../operator/"),
            base.replace(seam, "/x/%2e%2e/operator/"), base + ";x=1", base + "%00",
            base + "%20", base + "%2F", base.replace("-", "%2d"),
            base.replace("/" + last, "/" + last.title()),
            # C-1062 (reviewer C-839 P1): the CI log shows the edge's own 403 for these on every estate image
            "/" + base, "/." + base, base.replace(seam, "/operator%2f"), base + "."]


def _informational(prefix: str, route: str) -> list[str]:
    """Shapes sent and reported that fail the check only on a 2xx answer (C-671, reviewer C-650 F-C650-1): the CI
    log shows the service's own 404 for them, a harmless pass-through that must not turn CI red. A line
    ``info: ...: <status>`` in the job log shows what the edge did; promote a shape to ``_variants`` once the log
    shows 403 on every estate image."""
    base = f"/{prefix}/{route}" if prefix else f"/{route}"
    return [base.replace("/operator/", "/operator%252F"), base.replace("/operator/", "/operator\\")]


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
    leaks = []
    n = n_info = 0
    for prefix in PREFIXES:
        for method, route in ROUTES:
            for i, path in enumerate(_variants(prefix, route)):
                for spoof in ((False, True) if i == 0 else (False,)):
                    n += 1
                    status, body = _ask(base.rstrip("/") + path, method, secret, ctx, spoof)
                    if status != 403 or body.strip() != EDGE_BODY:
                        problems.append(f"{method} {path}{' (spoofed XFF)' if spoof else ''}: "
                                        f"{status} {body[:80]!r}")
            for path in _informational(prefix, route):
                n_info += 1
                status, body = _ask(base.rstrip("/") + path, method, secret, ctx, False)
                if status != 403 or body.strip() != EDGE_BODY:
                    print(f"info: {method} {path}: {status}")
                    if 200 <= status < 300:
                        leaks.append(f"{method} {path} (informational shape): {status} {body[:80]!r}")
    print(f"{n} requests to the internal routes through {base}: "
          f"{n - len(problems)} refused at the edge; {n_info} informational shapes sent")
    return problems + leaks


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
