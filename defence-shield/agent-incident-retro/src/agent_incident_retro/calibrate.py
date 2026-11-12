"""Threshold sweep against a labelled corpus (S4 B5).

The defaults (300 s pivot window, 1800 s session gap, 20 requests / CV 0.35
cadence) have no real corpus behind them. This module is the instrument that
will calibrate them: give it logs and a label file ``{"<client ip>": "rogue" |
"benign"}`` and it replays every combination in a grid, reporting per setting
how many labelled clients were flagged (ESCALATE or REVIEW) correctly.

It does not ship a corpus. The synthetic fixture in ``synth.py`` exercises the
code path only; numbers from it are not calibration.
"""

from __future__ import annotations

import argparse
import itertools
import json
from dataclasses import dataclass
from pathlib import Path

from .engine import run_retro
from .models import RetroConfig, Verdict

FLAGGED = {Verdict.ESCALATE, Verdict.REVIEW}
DEFAULT_GRID = {
    "pivot_window_s": [60.0, 300.0, 900.0],
    "session_gap_s": [600.0, 1800.0, 3600.0],
    "cadence_min_requests": [10, 20, 40],
    "cadence_cv_max": [0.2, 0.35, 0.5],
}


@dataclass(frozen=True)
class Point:
    config: dict
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def precision(self) -> float | None:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else None

    @property
    def recall(self) -> float | None:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else None


def sweep(paths: list[Path], labels: dict[str, str], grid: dict[str, list] | None = None, fmt: str = "clf") -> list[Point]:
    bad = {v for v in labels.values()} - {"rogue", "benign"}
    if bad:
        raise ValueError(f"labels must be 'rogue' or 'benign', got {sorted(bad)}")
    grid = grid or DEFAULT_GRID
    keys = list(grid)
    points = []
    for values in itertools.product(*(grid[k] for k in keys)):
        cfg = dict(zip(keys, values))
        result = run_retro(paths, fmt=fmt, config=RetroConfig(**cfg))
        flagged = {f.client_ip for f in result.findings if f.verdict in FLAGGED}
        tp = sum(1 for ip, lab in labels.items() if lab == "rogue" and ip in flagged)
        fn = sum(1 for ip, lab in labels.items() if lab == "rogue" and ip not in flagged)
        fp = sum(1 for ip, lab in labels.items() if lab == "benign" and ip in flagged)
        tn = sum(1 for ip, lab in labels.items() if lab == "benign" and ip not in flagged)
        points.append(Point(cfg, tp, fp, fn, tn))
    return points


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Sweep detection thresholds against a labelled corpus.")
    ap.add_argument("logs", nargs="+", type=Path)
    ap.add_argument("--labels", required=True, type=Path, help='JSON {"<ip>": "rogue"|"benign"}')
    ap.add_argument("--format", default="clf")
    args = ap.parse_args(argv)
    labels = json.loads(args.labels.read_text(encoding="utf-8"))
    for p in sweep(args.logs, labels, fmt=args.format):
        print(json.dumps({"config": p.config, "tp": p.tp, "fp": p.fp, "fn": p.fn, "tn": p.tn,
                          "precision": p.precision, "recall": p.recall}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
