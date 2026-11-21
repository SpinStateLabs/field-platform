"""Writes the SYNTHETIC calibration corpus: ``calibration.log`` and ``labels.json`` (C-1165, SPEC R-D4).

Nothing here is real traffic or a real incident. Every address is an RFC 5737 documentation address, every host and
user agent is fictional, and every payload is one of the canonical web-security test strings the synthetic demo log
already carries (``agent_incident_retro.synth``). The corpus exists so the detector's thresholds can be MEASURED
against actors whose ground truth is known by construction, which is what R-D4 says does not exist yet.

Each actor has a ``truth`` (what the scenario IS: ``rogue``, ``benign`` or ``authorized``), written here and never read
back from the detector. ``tests/test_calibration_corpus_c1165.py`` runs the retro over the log and compares.

Run from ``defence-shield/agent-incident-retro``:  python corpus/make_calibration_corpus.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from agent_incident_retro.synth import (  # noqa: E402
    ARCHIVE,
    CHROME,
    PROBE_PATHS,
    PY,
    SAFARI,
    SCANNER,
    SPOOFED_MARKER,
    SQLI,
    TRAVERSAL,
    XSS,
    _clf,
    _q,
)

START = datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc)
SIZE = 2048  # one fixed response size: the corpus has no random numbers at all

# ip -> (truth, scenario). The detector's behaviour is pinned in labels.json by the test, not here.
ACTORS = {
    "192.0.2.11": ("benign", "human browsing a record, 5 pages, a few seconds apart"),
    "192.0.2.12": ("benign", "human on a second browser, 7 pages"),
    "192.0.2.13": ("benign", "human with three mistyped addresses (404) then the right page"),
    "192.0.2.20": ("benign", "monitoring client polling one status path every 30 s, 30 requests"),
    "192.0.2.30": ("benign", "human whose search words look like a query keyword (select, union, drop in plain English)"),
    "198.51.100.200": ("benign", "archive crawler fetching 25 pages with a fixed gap"),
    "192.0.2.77": ("authorized", "a security scanner the owner authorised: hostile requests, allowed by IP"),
    "203.0.113.50": ("rogue", "fast pivot: benign search, then the same parameter carries a payload within a minute, then probes"),
    "203.0.113.51": ("rogue", "slow pivot: benign search, a long pause, the same parameter carries a payload after 400 s"),
    "203.0.113.60": ("rogue", "probe-only: three well-known probe paths from a scripting client, nothing else"),
    "203.0.113.77": ("rogue", "one-shot payload and a probe under a spoofed assistant marker in the user agent"),
    "203.0.113.90": ("rogue", "low and slow: one payload request every 2 hours, five times, each its own session"),
    "198.51.100.10": ("rogue", "rotated address 1 of 3 replaying one payload"),
    "198.51.100.11": ("rogue", "rotated address 2 of 3 replaying the same payload"),
    "198.51.100.12": ("rogue", "rotated address 3 of 3 replaying the same payload"),
}
BROWSE = ["/", "/about", "/collections", "/record/1043", "/record/2210", "/help", "/record/3377"]


def build() -> tuple[str, dict]:
    rows: list[tuple[datetime, str]] = []

    def add(ip, ts, target, status, ua, method="GET"):
        rows.append((ts, _clf(ip, ts, method, target, status, SIZE, ua)))

    def browse(ip, ua, t, pages, gaps):
        for i, page in enumerate(pages):
            add(ip, t, page, 200, ua)
            t += timedelta(seconds=gaps[i % len(gaps)])
        return t

    browse("192.0.2.11", CHROME, START + timedelta(minutes=3), BROWSE[:5], [6, 11, 4, 9])
    browse("192.0.2.12", SAFARI, START + timedelta(minutes=20), BROWSE[:7], [8, 5, 14, 7])
    t = START + timedelta(minutes=41)
    for typo in ("/colections", "/abuot", "/recrd/1043"):
        add("192.0.2.13", t, typo, 404, CHROME)
        t += timedelta(seconds=7)
    add("192.0.2.13", t, "/record/1043", 200, CHROME)
    t = START + timedelta(minutes=50)
    for _ in range(30):                                   # a poller: fixed 30 s cadence, one path
        add("192.0.2.20", t, "/status", 200, PY)
        t += timedelta(seconds=30)
    t = START + timedelta(hours=1)
    add("192.0.2.30", t, "/search?q=select+a+union+or+drop+by+date", 200, CHROME)
    add("192.0.2.30", t + timedelta(seconds=15), "/search?q=where+to+select+records", 200, CHROME)
    t = START + timedelta(hours=1, minutes=10)
    for page in range(25):                                # a crawler with a fixed 20 s gap
        add("198.51.100.200", t, f"/record/{2000 + page}", 200, ARCHIVE)
        t += timedelta(seconds=20)
    t = START + timedelta(hours=2)
    for path in PROBE_PATHS + [f"/search?q={_q(XSS)}"]:
        add("192.0.2.77", t, path, 403, SCANNER)
        t += timedelta(seconds=9)

    t = START + timedelta(hours=3)
    add("203.0.113.50", t, "/search?q=divorce+records+1905", 200, CHROME)
    add("203.0.113.50", t + timedelta(seconds=20), "/search?q=divorce+1905+ontario", 404, CHROME)
    add("203.0.113.50", t + timedelta(seconds=45), f"/search?q={_q(SQLI)}", 200, CHROME)
    add("203.0.113.50", t + timedelta(seconds=63), f"/search?q={_q(XSS)}", 200, CHROME)
    t += timedelta(seconds=85)
    for path in PROBE_PATHS:
        add("203.0.113.50", t, path, 404, CHROME)
        t += timedelta(seconds=15)
    t = START + timedelta(hours=4)
    add("203.0.113.51", t, "/search?q=divorce+records+1905", 200, CHROME)
    add("203.0.113.51", t + timedelta(seconds=30), "/search?q=divorce+1905+ontario", 404, CHROME)
    add("203.0.113.51", t + timedelta(seconds=430), f"/search?q={_q(SQLI)}", 200, CHROME)
    t = START + timedelta(hours=5)
    for path in PROBE_PATHS:
        add("203.0.113.60", t, path, 404, PY)
        t += timedelta(seconds=12)
    t = START + timedelta(hours=6)
    add("203.0.113.77", t, f"/lookup?id={_q(SQLI)}", 500, SPOOFED_MARKER)
    add("203.0.113.77", t + timedelta(seconds=40), "/.env", 404, SPOOFED_MARKER)
    for hour in range(5):                                 # low and slow: sessions never touch (gap far above 1800 s)
        add("203.0.113.90", START + timedelta(hours=7 + 2 * hour), f"/files?name={_q(TRAVERSAL)}", 200, CHROME)
    union = "1 UNION SELECT username,password FROM users"
    for i, ip in enumerate(("198.51.100.10", "198.51.100.11", "198.51.100.12")):
        t = START + timedelta(hours=18, minutes=7 * i)
        add(ip, t, f"/item?id={_q(union)}", 200, PY)
        add(ip, t + timedelta(seconds=30), "/item?id=42", 200, PY)

    rows.sort(key=lambda r: (r[0], r[1]))
    log = "\n".join(line for _, line in rows) + "\n"
    labels = {"synthetic": True, "actors": {ip: {"truth": truth, "scenario": scenario}
                                            for ip, (truth, scenario) in ACTORS.items()}}
    return log, labels


def main() -> None:
    log, labels = build()
    (HERE / "calibration.log").write_text(log, encoding="utf-8", newline="\n")
    (HERE / "labels.json").write_text(json.dumps(labels, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(log.splitlines())} log lines and {len(labels['actors'])} labelled actors")


if __name__ == "__main__":
    main()
