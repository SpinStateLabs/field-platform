"""TokenStore under concurrent reads and writes.

The store holds ONE sqlite3 connection (``check_same_thread=False``) shared by
every FastAPI request thread. Before v1.2 hardening only writes took
``_lock``; unlocked concurrent reads came back as spurious
``TokenNotFoundError`` (an unknown token introspects as inactive), as ANOTHER
token's row (which carries another token's grant), or as decode errors.

This test drives 8 threads through the public methods in phases (one per
read query, every thread running it with a write mixed in, then one mixed
phase) and counts both exceptions and wrong answers (a ``get(id)`` whose
token is not ``id``, a ``list(agent)`` holding another agent's token). It
fails every time on a copy of the store with the lock removed from the
reads, and on copies with the lock removed from any ONE read.
Bounded: fixed thread and iteration counts, and ONE 60 s join budget per
phase (not 60 s per thread) that turns a deadlock into a failure.
"""

from __future__ import annotations

import threading
import time
from collections import Counter
from datetime import datetime, timedelta, timezone

from delegation_authority.store import TokenNotFoundError, TokenStore
from field_core.delegation import DelegationToken

THREADS = 8
ITERS = 150  # per thread, per phase
WRITE_EVERY = 40  # one write in every 40 ops of a read phase
TOKENS = 40
AGENTS = 8


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


def test_concurrent_reads_and_writes_return_the_right_token(tmp_path):
    store = TokenStore(tmp_path / "tokens.sqlite3")
    now = datetime.now(timezone.utc)

    def make(i: int, token_id: str | None = None) -> DelegationToken:
        extra = {"token_id": token_id} if token_id else {}
        return DelegationToken(
            agent_id=f"agent-{i % AGENTS}", granted_by=f"grantor-{i}",
            scope=[f"scope-{i}"], issued_at=now + timedelta(seconds=i),
            expires_at=now + timedelta(days=1), **extra,
        )

    ids = [store.save(make(i)).token_id for i in range(TOKENS)]
    index = {tid: i for i, tid in enumerate(ids)}

    def mismatch(t: DelegationToken) -> str | None:
        i = index.get(t.token_id)
        if i is None:
            return f"unknown_token_id: {t.token_id}"
        if (t.agent_id, t.granted_by, t.scope) != (
            f"agent-{i % AGENTS}", f"grantor-{i}", [f"scope-{i}"]
        ):
            return f"mixed_row: {t.token_id} {t.agent_id} {t.granted_by} {t.scope}"
        return None

    def op_get(k, n):
        i = (k * 7 + n) % TOKENS
        try:
            t = store.get(ids[i])
        except TokenNotFoundError:
            return f"spurious_not_found: token {i}"
        if t.token_id != ids[i]:
            return f"wrong_row: asked {i} got {index.get(t.token_id)}"
        return mismatch(t)

    def op_list_agent(k, n):
        agent = f"agent-{(k + n) % AGENTS}"
        toks = store.list(agent)
        if len(toks) != TOKENS // AGENTS:
            return f"list_wrong_count: {agent} {len(toks)}"
        for t in toks:
            if t.agent_id != agent:
                return f"list_wrong_agent: {agent} got {t.agent_id}"
            if problem := mismatch(t):
                return problem
        return None

    def op_list_all(k, n):
        toks = store.list()
        if len(toks) != TOKENS:
            return f"list_all_wrong_count: {len(toks)}"
        return next((p for p in map(mismatch, toks) if p), None)

    def op_active(k, n):
        agent = f"agent-{(k + n) % AGENTS}"
        toks = store.active_tokens_for(agent)
        if len(toks) != TOKENS // AGENTS:
            return f"active_wrong_count: {agent} {len(toks)}"
        return next((p for p in map(mismatch, toks) if p), None)

    def op_save(k, n):
        i = (k * 3 + n) % TOKENS
        store.save(make(i, token_id=ids[i]))  # same identity, rewritten
        return None

    # One phase per read query, so each races copies of ITSELF (the sharpest
    # interleaving) with writes mixed in; then one mixed phase.
    phases = [[read] * (WRITE_EVERY - 1) + [op_save]
              for read in (op_get, op_list_agent, op_list_all, op_active)]
    phases.append([op_get, op_list_agent, op_get, op_list_all, op_active] * 4 + [op_save])

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
        final = store.list()
        assert len(final) == TOKENS and not any(map(mismatch, final))
    finally:
        if not hung:  # a deadlocked worker still holds the lock close() needs
            store.close()
