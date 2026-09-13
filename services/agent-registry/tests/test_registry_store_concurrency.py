"""RegistryStore under concurrent reads and writes.

The store holds ONE sqlite3 connection (``check_same_thread=False``) shared by
every FastAPI request thread. Before v1.2 hardening only writes took
``_lock``; unlocked concurrent reads came back as spurious
``AgentNotFoundError``, as ANOTHER agent's record, or as decode errors — and
because ``update``/``attest`` read the record before writing it, a wrong-row
read was PERSISTED: one agent's row ended up carrying another agent's
name/owner/domain.

This test drives 8 threads through the public methods in phases (one per
read query, every thread running it with an update or attest mixed in, then
one mixed phase), counts exceptions and wrong answers, then checks every
persisted row. It fails every time on a copy of the store with the lock
removed from the reads, and on copies with the lock removed from any ONE
read. Bounded: fixed thread and iteration counts, and ONE 60 s join budget
per phase (not 60 s per thread) that turns a deadlock into a failure.
"""

from __future__ import annotations

import threading
import time
from collections import Counter

from agent_registry.models import AgentCreate, AgentRecord, AgentStatus, AgentUpdate
from agent_registry.store import AgentNotFoundError, RegistryStore

THREADS = 8
ITERS = 150  # per thread, per phase
WRITE_EVERY = 40  # one write in every 40 ops of a read phase
AGENTS = 40
DOMAINS = 4


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


def _mismatch(rec: AgentRecord, expect: int | None = None) -> str | None:
    """None if the record is self-consistent (and is agent ``expect``)."""
    try:
        i = int(rec.agent_id.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return f"unknown_agent_id: {rec.agent_id}"
    if expect is not None and i != expect:
        return f"wrong_row: asked agent-{expect} got {rec.agent_id}"
    if (rec.name, rec.owner, rec.domain, rec.status) != (
        f"name-{i}", f"owner-{i}", f"d{i % DOMAINS}", AgentStatus.ACTIVE
    ):
        return f"mixed_row: {rec.agent_id} {rec.name} {rec.owner} {rec.domain} {rec.status}"
    return None


def test_concurrent_reads_and_writes_return_and_persist_the_right_agent(tmp_path):
    store = RegistryStore(tmp_path / "agents.sqlite3")
    for i in range(AGENTS):
        store.add(AgentCreate(agent_id=f"agent-{i}", name=f"name-{i}",
                              owner=f"owner-{i}", domain=f"d{i % DOMAINS}"))

    def op_get(k, n):
        i = (k * 7 + n) % AGENTS
        try:
            return _mismatch(store.get(f"agent-{i}"), i)
        except AgentNotFoundError:
            return f"spurious_not_found: agent-{i}"

    def op_list_domain(k, n):
        domain = f"d{(k + n) % DOMAINS}"
        recs = store.list(domain=domain)
        if len(recs) != AGENTS // DOMAINS:
            return f"list_wrong_count: {domain} {len(recs)}"
        for r in recs:
            if r.domain != domain:
                return f"list_wrong_domain: {domain} got {r.domain}"
            if problem := _mismatch(r):
                return problem
        return None

    def op_list_active(k, n):
        recs = store.list(status=AgentStatus.ACTIVE)
        if len(recs) != AGENTS:
            return f"list_active_wrong_count: {len(recs)}"
        return next((p for p in map(_mismatch, recs) if p), None)

    def op_update(k, n):  # read-then-write through the public method
        i = (k * 3 + n) % AGENTS
        try:
            rec = store.update(f"agent-{i}", AgentUpdate(manifest_ref=f"ref-{k}-{n}"))
        except AgentNotFoundError:
            return f"update_spurious_not_found: agent-{i}"
        return _mismatch(rec, i)

    def op_attest(k, n):
        i = (k * 5 + n) % AGENTS
        try:
            return _mismatch(store.attest(f"agent-{i}", f"attester-{k}"), i)
        except AgentNotFoundError:
            return f"attest_spurious_not_found: agent-{i}"

    # One phase per read query, so each races copies of ITSELF (the sharpest
    # interleaving) with writes mixed in; then one mixed phase.
    reads = [op_get, op_list_domain, op_list_active]
    writes = [op_update, op_attest]
    phases = [[read] * (WRITE_EVERY - 1) + [writes[j % 2]] for j, read in enumerate(reads)]
    phases.append([op_get, op_list_domain, op_get, op_list_active] * 5 + writes)

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
        persisted = store.list()
        corrupted = [p for p in map(_mismatch, persisted) if p]
        assert len(persisted) == AGENTS and not corrupted, corrupted[:5]
    finally:
        if not hung:  # a deadlocked worker still holds the lock close() needs
            store.close()
