"""Larger deterministic SYNTHETIC labelled corpus (S4 B5) for regression tests of the sweep.

Nothing here is real traffic and NOTHING here calibrates a threshold: the four
defaults stay uncalibrated until real labelled logs exist (todo 287). This
corpus only pins the plumbing and the detector's behaviour on a bigger, varied
population (hundreds of humans, several rogue shapes, a few awkward benign
clients) so a regression in clause logic or in ``calibrate.sweep`` shows up.

IPs are RFC 5737 documentation ranges. Returns ``(log_text, labels)`` where
labels is ``{"<ip>": "rogue" | "benign"}``.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from .synth import CHROME, PY, SAFARI, SQLI, XSS, _clf, _q

PAGES = ["/", "/about", "/collections", "/search?q=census+1911", "/search?q=parish+records",
         "/record/1043", "/record/2210", "/help", "/search?q=ship+manifests"]


def generate_corpus(seed: int = 11, humans: int = 300, pivoters: int = 12, cadence_bots: int = 8,
                    start: datetime | None = None) -> tuple[str, dict[str, str]]:
    rng = random.Random(seed)
    t0 = start or datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
    rows: list[tuple[datetime, str]] = []
    labels: dict[str, str] = {}

    def add(ip, ts, target, status, ua):
        rows.append((ts, _clf(ip, ts, "GET", target, status, rng.randint(300, 9000), ua)))

    # benign humans: irregular, 4-14 page views, 192.0.2.0/24 then 198.51.100.0/24
    for h in range(humans):
        ip = f"192.0.2.{h % 250 + 1}" if h < 250 else f"198.51.100.{h - 250 + 1}"
        labels[ip] = "benign"
        ts = t0 + timedelta(minutes=rng.randint(0, 1400))
        for _ in range(rng.randint(4, 14)):
            add(ip, ts, rng.choice(PAGES), rng.choice([200, 200, 200, 304, 404]), CHROME if h % 2 else SAFARI)
            ts += timedelta(seconds=rng.randint(4, 120))

    # rogue pivoters: benign search, then the SAME parameter carries a payload, within 20-250 s
    for i in range(pivoters):
        ip = f"203.0.113.{10 + i}"
        labels[ip] = "rogue"
        ts = t0 + timedelta(minutes=rng.randint(0, 1400))
        add(ip, ts, f"/search?q=surname+{i}", 200, CHROME)
        ts += timedelta(seconds=rng.randint(20, 250))
        add(ip, ts, f"/search?q={_q(SQLI if i % 2 else XSS)}", 200, CHROME)

    # rogue cadence bots: 30-60 requests at a near-constant interval, then one debug probe
    for i in range(cadence_bots):
        ip = f"203.0.113.{100 + i}"
        labels[ip] = "rogue"
        ts = t0 + timedelta(minutes=rng.randint(0, 1000))
        step = rng.choice([5, 8, 12])
        for k in range(rng.randint(30, 60)):
            add(ip, ts, f"/record/{3000 + k}", 200, PY)
            ts += timedelta(seconds=step + rng.choice([0, 0, 1]))
        # cadence alone is never flagged (verdict needs a hostile request), so each bot also probes once
        add(ip, ts, "/.env", 404, PY)

    rows.sort(key=lambda r: r[0])
    return "\n".join(line for _, line in rows) + "\n", labels
