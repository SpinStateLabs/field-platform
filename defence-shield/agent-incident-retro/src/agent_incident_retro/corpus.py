"""Larger LABELLED SYNTHETIC corpus for exercising ``calibrate.sweep`` (S4 B5).

REGRESSION INSTRUMENT, NOT CALIBRATION. Every label here is true by
construction because this module wrote the traffic; real engagements do not
look like this, so a threshold that scores well on it is not thereby correct.
It exists to (a) prove the sweep and the detector agree end to end at scale
and (b) pin how the four defaults behave on borderline shapes (slow pivots,
regular crawlers). Real calibration still needs real labelled logs.

All addresses are RFC 5737 documentation ranges; the host is fictional.
Behaviour classes (label in brackets):

* humans: short irregular browsing [benign]
* mirror crawlers: long, regular, benign requests (cadence false-positive probe) [benign]
* archive fetchers: replay a payload URL once [benign; the detector flags them REVIEW via S.launder
  by design, so they are the corpus's known false positives]
* fast agents: benign search then payload on the same parameter inside the pivot window [rogue]
* slow agents: the same pivot spaced 120-280 s apart (inside the default window) [rogue]
* patient agents: the pivot spaced 400-900 s apart (outside the default window) [rogue]
* scanners: probe paths and payloads in quick succession [rogue]
* rotated-IP campaigns: one union payload replayed from three addresses [rogue]
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from .synth import ARCHIVE, CHROME, PROBE_PATHS, PY, SAFARI, SCANNER, SQLI, XSS, _clf, _q

COUNTS = {
    "human": 30, "mirror": 4, "archive": 3, "fast": 8, "slow": 8, "patient": 6, "scanner": 5, "campaign": 3,
}
_UNION = "1 UNION SELECT username,password FROM users"


def _addresses():
    for net in ("192.0.2", "198.51.100", "203.0.113"):
        for host in range(1, 255):
            yield f"{net}.{host}"


def generate_corpus(seed: int = 11, scale: int = 1) -> tuple[str, dict[str, str]]:
    """Return (combined-format log text, {ip: 'rogue' | 'benign'}). ``scale`` multiplies each class."""
    rng = random.Random(seed)
    t0 = datetime(2026, 9, 1, 8, 0, 0, tzinfo=timezone.utc)
    pool = _addresses()
    rows: list[tuple[datetime, str]] = []
    labels: dict[str, str] = {}

    def ip_for(label: str) -> str:
        ip = next(pool)
        labels[ip] = label
        return ip

    def add(ip, ts, target, status, ua):
        rows.append((ts, _clf(ip, ts, "GET", target, status, rng.randint(300, 9000), ua)))

    def start() -> datetime:
        return t0 + timedelta(minutes=rng.randint(0, 900))

    pages = ["/", "/about", "/collections", "/search?q=census+1911", "/record/1043", "/record/2210", "/help"]
    for _ in range(COUNTS["human"] * scale):
        ip, ts = ip_for("benign"), start()
        for _ in range(rng.randint(4, 14)):
            add(ip, ts, rng.choice(pages), rng.choice([200, 200, 304, 404]), rng.choice([CHROME, SAFARI]))
            ts += timedelta(seconds=rng.randint(4, 90))
    for _ in range(COUNTS["mirror"] * scale):  # regular cadence, benign paths
        ip, ts = ip_for("benign"), start()
        gap = rng.choice([5, 10, 30])
        for n in range(rng.randint(30, 80)):
            add(ip, ts, f"/record/{1000 + n}", 200, PY)
            ts += timedelta(seconds=gap, milliseconds=rng.randint(0, 400))
    for _ in range(COUNTS["archive"] * scale):
        add(ip_for("benign"), start(), f"/search?q={_q(SQLI)}", 200, ARCHIVE)

    def pivot(ip, ts, gap_lo, gap_hi, ua):
        add(ip, ts, "/search?q=parish+records", 200, ua)
        ts += timedelta(seconds=rng.randint(gap_lo, gap_hi))
        add(ip, ts, f"/search?q={_q(SQLI)}", 200, ua)
        ts += timedelta(seconds=rng.randint(gap_lo, gap_hi))
        add(ip, ts, f"/search?q={_q(XSS)}", 200, ua)

    for _ in range(COUNTS["fast"] * scale):
        pivot(ip_for("rogue"), start(), 5, 40, PY)
    for _ in range(COUNTS["slow"] * scale):
        pivot(ip_for("rogue"), start(), 120, 280, CHROME)
    for _ in range(COUNTS["patient"] * scale):
        pivot(ip_for("rogue"), start(), 400, 900, CHROME)
    for _ in range(COUNTS["scanner"] * scale):
        ip, ts = ip_for("rogue"), start()
        for p in PROBE_PATHS + [f"/search?q={_q(XSS)}"]:
            add(ip, ts, p, rng.choice([200, 403, 404]), SCANNER)
            ts += timedelta(seconds=rng.randint(2, 15))
    for _ in range(COUNTS["campaign"] * scale):
        base = start()
        for i in range(3):
            ip = ip_for("rogue")
            add(ip, base + timedelta(minutes=i * 7), f"/item?id={_q(_UNION)}", 200, PY)
    rows.sort(key=lambda r: r[0])
    return "\n".join(line for _, line in rows) + "\n", labels
