"""Persistent gateway telemetry (v1.2 D2c) — one SQLite file per data dir.

``$FIELD_DATA_DIR/gateway/telemetry.sqlite3`` (``./var`` when the variable is
unset, the governor's convention) holds three tables:

* ``telemetry_records`` — one row per instrumented response (metadata and
  counters only; never response text). Pruned to the newest
  ``max(retain, N)`` rows (``FORCE_TELEMETRY_RETAIN``, ``N`` = the
  ``last_N`` window) plus each route's own newest ``N``: ``recent`` and the
  ``last_N`` rate windows read these rows.
* ``drift_scores`` — append-only judged scores ``(route, dimension, score,
  model, rubric, ts)``; replayed in order into a fresh ``DriftTracker`` at
  startup, which rebuilds baselines and alert state deterministically.
* ``counters`` — named integers: the sampling stride (``request_count``),
  the coverage counters, and the cumulative per-route aggregates behind the
  totals and the ``all`` rate window (so pruning never shrinks a total).
  ``bypass_remaining`` is NOT persisted: a restart re-arms instrumentation.

One connection shared by the request threads, every use under ``_lock``
(the spend-governor store's pattern). Any sqlite error propagates: the
gateway treats a store fault like any instrumentation fault (bypass).
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

DEFAULT_RETAIN = 10_000

#: cumulative per-route aggregate counters, ``agg.<route>.<field>``
AGG_FIELDS = ("requests", "confidence_tags", "clean_of_flattery", "cot_structure",
              "corrections", "input_tokens", "output_tokens")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS telemetry_records (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    route TEXT NOT NULL,
    record TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_telemetry_records_route ON telemetry_records(route, seq);
CREATE TABLE IF NOT EXISTS drift_scores (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    route TEXT NOT NULL,
    dimension TEXT NOT NULL,
    score REAL NOT NULL,
    model TEXT NOT NULL,
    rubric TEXT NOT NULL,
    ts TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS counters (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
"""


def data_path() -> Path:
    root = Path(os.environ.get("FIELD_DATA_DIR", "./var"))
    return root / "gateway" / "telemetry.sqlite3"


def resolve_retain(default: int = DEFAULT_RETAIN) -> int:
    """``FORCE_TELEMETRY_RETAIN``: rows kept in ``telemetry_records`` (>= 1;
    junk falls back to the default)."""
    try:
        return max(1, int(os.environ.get("FORCE_TELEMETRY_RETAIN", "")))
    except ValueError:
        return default


class GatewayStore:
    def __init__(self, path: str | Path, retain: int | None = None):
        self.path = Path(path)
        self.retain = retain if retain is not None else resolve_retain()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        try:
            with self._lock, self._conn:
                self._conn.executescript(_SCHEMA)
        except Exception:
            self._conn.close()
            raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # -- counters --
    def incr(self, name: str, by: int = 1) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO counters(name, value) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET value = value + excluded.value",
                (name, by))

    def counters(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn.execute("SELECT name, value FROM counters").fetchall()
        return {name: int(value) for name, value in rows}

    # -- one instrumented request --
    def commit_request(self, route: str, record: dict[str, Any],
                       agg: dict[str, int], counters: dict[str, int],
                       drift_scores: list[tuple[str, str, float, str, str]],
                       ts: str, keep_at_least: int = 0) -> None:
        """Insert the record, bump its route's aggregates and the request's
        counters, append its judged scores, prune — ONE transaction, so a
        total, its rows and the replayable scores never disagree.

        Pruning keeps the newest ``max(retain, keep_at_least)`` rows AND each
        route's own newest ``keep_at_least`` rows, so a quiet route's
        ``last_N`` window is never emptied by a busy one: at most
        ``max(retain, N) + routes * N`` rows (routes = the presets)."""
        keep = max(self.retain, keep_at_least)
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO telemetry_records(route, record) VALUES (?, ?)",
                (route, json.dumps(record, sort_keys=True)))
            bumps = {f"agg.{route}.{fld}": int(v) for fld, v in agg.items()}
            for name, value in counters.items():
                bumps[name] = bumps.get(name, 0) + int(value)
            for name, value in bumps.items():
                self._conn.execute(
                    "INSERT INTO counters(name, value) VALUES (?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET value = value + excluded.value",
                    (name, value))
            for s_route, dimension, score, model, rubric in drift_scores:
                self._conn.execute(
                    "INSERT INTO drift_scores(route, dimension, score, model, "
                    "rubric, ts) VALUES (?, ?, ?, ?, ?, ?)",
                    (s_route, dimension, float(score), model, rubric, ts))
            self._prune(cur.lastrowid - keep, keep_at_least)

    def _prune(self, cutoff: int, per_route: int) -> None:
        """Delete rows older than the global ``cutoff`` seq that are also
        outside their route's newest ``per_route`` rows (caller holds the
        lock and the transaction)."""
        if cutoff <= 0:
            return
        if per_route <= 0:
            self._conn.execute("DELETE FROM telemetry_records WHERE seq <= ?", (cutoff,))
            return
        routes = [route for (route,) in self._conn.execute(
            "SELECT DISTINCT route FROM telemetry_records WHERE seq <= ?", (cutoff,))]
        for route in routes:
            floor = self._conn.execute(
                "SELECT seq FROM telemetry_records WHERE route = ? "
                "ORDER BY seq DESC LIMIT 1 OFFSET ?", (route, per_route - 1)).fetchone()
            if floor is None:
                continue  # the route holds no more than its window: keep it all
            self._conn.execute(
                "DELETE FROM telemetry_records WHERE route = ? AND seq <= ? AND seq < ?",
                (route, cutoff, floor[0]))

    def records(self, limit: int | None = None,
                route: str | None = None) -> list[dict[str, Any]]:
        """Newest ``limit`` retained records (all when None), oldest first."""
        sql = "SELECT record FROM telemetry_records"
        args: list[Any] = []
        if route is not None:
            sql += " WHERE route = ?"
            args.append(route)
        sql += " ORDER BY seq DESC"
        if limit is not None:
            sql += " LIMIT ?"
            args.append(max(0, int(limit)))
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [json.loads(r[0]) for r in reversed(rows)]

    # -- drift scores --
    def drift_scores(self) -> list[tuple[str, str, float, str, str]]:
        """Every judged score, in the order it was committed (replay input)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT route, dimension, score, model, rubric FROM drift_scores "
                "ORDER BY seq").fetchall()
        return [(route, dimension, float(score), model, rubric)
                for route, dimension, score, model, rubric in rows]
