"""Deterministic SYNTHETIC combined-format log for the demo and tests.

Nothing here is real traffic. IPs are RFC 5737 documentation ranges and the
host is fictional. The tool under test is a *detector*; this fixture is the
labelled input it must flag. Payload tokens are drawn from a short table of
canonical, widely-published web-security test strings (the kind every WAF
test suite carries) so the fixture exercises the classifier without being a
how-to for anything.

Expected verdicts are pinned by ``tests/test_synth_expectations.py``.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

CHROME = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0.0.0 Safari/537.36"
SAFARI = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 Version/17.5 Safari/605.1.15"
# A deliberately SPOOFED marker: it shows G2 is a claim, not proof of operator.
SPOOFED_MARKER = "Mozilla/5.0 (compatible; ChatGPT-User/1.0; synthetic-spoof-for-test)"
PY = "python-requests/2.32.3"
ARCHIVE = "Mozilla/5.0 (compatible; archive.org_bot +http://archive.org/details/archive.org_bot)"
SCANNER = "Mozilla/5.0 (compatible; ExampleSec-Scanner/3.1; authorized-test)"

AGENT_A_IP = "203.0.113.50"
AGENT_B_IP = "203.0.113.77"
ROTATED_IPS = ["198.51.100.10", "198.51.100.11", "198.51.100.12"]
ARCHIVE_IP = "198.51.100.200"
SCANNER_IP = "192.0.2.77"

# Canonical test tokens (one representative per family). Kept terse on purpose.
SQLI = "' OR '1'='1"
XSS = "<script>alert(1)</script>"
TRAVERSAL = "../../etc/passwd"
PROBE_PATHS = ["/.env", "/actuator/env", "/admin/"]


def _clf(ip, ts, method, target, status, size, ua, ref="-"):
    stamp = ts.strftime("%d/%b/%Y:%H:%M:%S +0000")
    return f'{ip} - - [{stamp}] "{method} {target} HTTP/1.1" {status} {size} "{ref}" "{ua}"'


def _q(value: str) -> str:
    return quote(value, safe="")


def generate(seed: int = 7, start: datetime | None = None) -> str:
    rng = random.Random(seed)
    t0 = start or datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc)
    rows: list[tuple[datetime, str]] = []

    def add(ip, ts, target, status, ua, method="GET"):
        rows.append((ts, _clf(ip, ts, method, target, status, rng.randint(300, 9000), ua)))

    # --- 30 ordinary human browsing sessions -> CLEAR
    pages = ["/", "/about", "/collections", "/search?q=census+1911",
             "/search?q=parish+records", "/record/1043", "/record/2210", "/help"]
    for h in range(30):
        ip, ua = f"192.0.2.{100 + h}", (CHROME if h % 2 else SAFARI)
        ts = t0 + timedelta(minutes=rng.randint(0, 600))
        for _ in range(rng.randint(4, 14)):
            add(ip, ts, rng.choice(pages), rng.choice([200, 200, 200, 304, 404]), ua)
            ts += timedelta(seconds=rng.randint(4, 90))

    # --- agent A: benign search, then tamper the same param, then probes -> ESCALATE, G1
    ts = t0 + timedelta(hours=2)
    add(AGENT_A_IP, ts, "/search?q=divorce+records+1905", 200, CHROME)
    ts += timedelta(seconds=20)
    add(AGENT_A_IP, ts, "/search?q=divorce+1905+ontario", 404, CHROME)
    ts += timedelta(seconds=25)  # escalate on the 404, same param now carries a payload
    add(AGENT_A_IP, ts, f"/search?q={_q(SQLI)}", 200, CHROME)
    ts += timedelta(seconds=18)
    add(AGENT_A_IP, ts, f"/search?q={_q(XSS)}", 200, CHROME)
    ts += timedelta(seconds=22)
    for p in PROBE_PATHS:
        add(AGENT_A_IP, ts, p, rng.choice([200, 403, 404]), CHROME)
        ts += timedelta(seconds=rng.randint(10, 40))
    add(AGENT_A_IP, ts, f"/files?name={_q(TRAVERSAL)}", 200, CHROME)

    # --- agent B: one-shot payloads under a SPOOFED marker UA -> REVIEW, G2
    ts = t0 + timedelta(hours=4)
    add(AGENT_B_IP, ts, f"/lookup?id={_q(SQLI)}", 500, SPOOFED_MARKER)
    ts += timedelta(seconds=40)
    add(AGENT_B_IP, ts, "/.env", 404, SPOOFED_MARKER)

    # --- three rotated IPs replay the SAME UNION payload -> one campaign, REVIEW/G1
    union = "1 UNION SELECT username,password FROM users"
    for i, ip in enumerate(ROTATED_IPS):
        ts = t0 + timedelta(hours=5, minutes=i * 7)
        add(ip, ts, f"/item?id={_q(union)}", 200, PY)
        ts += timedelta(seconds=30)
        add(ip, ts, "/item?id=42", 200, PY)

    # --- archive fetcher replays a payload URL -> REVIEW via S.launder
    ts = t0 + timedelta(hours=6)
    add(ARCHIVE_IP, ts, f"/search?q={_q(SQLI)}", 200, ARCHIVE)

    # --- a scanner: hostile; AUTHORIZED only if the caller allowlists its IP -> else ESCALATE
    ts = t0 + timedelta(hours=7)
    for p in PROBE_PATHS + [f"/search?q={_q(XSS)}"]:
        add(SCANNER_IP, ts, p, rng.choice([200, 403, 404]), SCANNER)
        ts += timedelta(seconds=rng.randint(5, 20))

    rows.sort(key=lambda r: r[0])
    out = [line for _, line in rows]
    # two malformed lines -> counted unparsed, never fatal
    out.insert(5, "this is not a log line at all")
    out.insert(len(out) // 2, '203.0.113.9 - - [bad-timestamp] "GET /x HTTP/1.1" 200 10 "-" "-"')
    return "\n".join(out) + "\n"
