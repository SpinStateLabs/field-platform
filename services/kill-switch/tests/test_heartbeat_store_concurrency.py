"""HeartbeatStore under concurrent reads and writes.

The store holds ONE sqlite3 connection (``check_same_thread=False``) shared by
every FastAPI request thread. Before v1.2 hardening only ``record`` took
``_lock``; unlocked concurrent reads came back as ``None`` for an agent that
HAD checked in (liveness would call it never-seen), as ANOTHER agent's row,
or as decode errors.

This test drives 8 threads through the public methods in phases (one per
read query, every thread running it with a check-in mixed in, then one mixed
phase), counts exceptions and wrong answers, then checks that every check-in
was counted exactly once. It fails every time on a copy of the store with the
lock removed from the reads, and on copies with the lock removed from any ONE
read. Bounded: fixed thread and iteration counts, and ONE 60 s join budget
per phase (not 60 s per thread) that turns a deadlock into a failure.
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from datetime import datetime, timezone

from kill_switch.store import HeartbeatStore

THREADS = 8
ITERS = 150  # per thread, per phase
WRITE_EVERY = 40  # one write in every 40 ops of a read phase
AGENTS = 40


def _hammer(ops, threads=THREADS, iters=ITERS):
    anomalies: Counter[str] = Counter()
    examples: list[str] = []
    guard = threading.Lock()
    barrier = threading.Barrier(threads)

    def worker(k: int) -> None:
        barrier.wait()
        for n in range(iters):
            try:
                problem = ops[(k + n) % len(ops)](k, n)
            except Exception as exc:  # every exception is an anomaly here
                problem = f"{type(exc).__name__}: {exc}"
            if problem:
                with guard:
                    anomalies[problem.split(":", 1)[0]] += 1
                    if len(examples) < 5:
                        examples.append(problem[:160])

    pool = [threading.Thread(target=worker, args=(k,), daemon=True) for k in range(threads)]
    for t in pool:
        t.start()
    deadline = time.monotonic() + 60  # ONE budget for the pool, not 60 s per thread
    for t in pool:
        t.join(timeout=max(0.0, deadline - time.monotonic()))
    hung = sum(t.is_alive() for t in pool)
    return anomalies, examples, hung


def _mismatch(row: dict, expect: str | None = None) -> str | None:
    agent = row.get("agent_id")
    if expect is not None and agent != expect:
        return f"wrong_row: asked {expect} got {agent}"
    try:
        i = int(str(agent).rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return f"unknown_agent_id: {agent}"
    if row.get("status") != f"st-{i}":
        return f"mixed_row: {agent} {row.get('status')}"
    if not isinstance(row.get("last_seen"), datetime) or not isinstance(row.get("checkins"), int):
        return f"bad_types: {row!r}"
    return None


def test_concurrent_checkins_and_reads_return_the_right_agent(tmp_path):
    store = HeartbeatStore(tmp_path / "hb.sqlite3")
    seen = datetime.now(timezone.utc)
    expected = Counter()
    for i in range(AGENTS):
        store.record(f"agent-{i}", seen, f"st-{i}")
        expected[f"agent-{i}"] += 1
    counted = threading.Lock()

    def op_get(k, n):
        agent = f"agent-{(k * 7 + n) % AGENTS}"
        row = store.get(agent)
        if row is None:
            return f"spurious_none: {agent} has checked in"
        return _mismatch(row, agent)

    def op_all(k, n):
        rows = store.all()
        if len(rows) != AGENTS:
            return f"all_wrong_count: {len(rows)}"
        for key, row in rows.items():
            if key != row["agent_id"]:
                return f"all_key_mismatch: {key} {row['agent_id']}"
            if problem := _mismatch(row):
                return problem
        return None

    def op_record(k, n):
        i = (k * 3 + n) % AGENTS
        store.record(f"agent-{i}", datetime.now(timezone.utc), f"st-{i}")
        with counted:
            expected[f"agent-{i}"] += 1
        return None

    # One phase per read query, so each races copies of ITSELF (the sharpest
    # interleaving) with writes mixed in; then one mixed phase.
    phases = [[read] * (WRITE_EVERY - 1) + [op_record] for read in (op_get, op_all)]
    phases.append([op_get, op_all, op_get, op_get] * 5 + [op_record])

    anomalies: Counter[str] = Counter()
    examples: list[str] = []
    hung = 0
    for ops in phases:
        found, seen, hung = _hammer(ops)
        anomalies.update(found)
        examples.extend(seen[: 5 - len(examples)])
        if hung:
            break

    try:
        assert hung == 0, f"{hung} worker thread(s) still running after 60 s: deadlock"
        total = THREADS * ITERS * len(phases)
        assert not anomalies, (
            f"{sum(anomalies.values())} anomalies in {total} concurrent store "
            f"calls: {dict(anomalies)}; e.g. {examples}"
        )
        rows = store.all()
        assert {a: r["checkins"] for a, r in rows.items()} == dict(expected)
    finally:
        if not hung:  # a deadlocked worker still holds the lock close() needs
            store.close()
