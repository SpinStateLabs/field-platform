"""ContractStore under concurrent reads and writes.

The store holds ONE sqlite3 connection (``check_same_thread=False``) shared by
every FastAPI request thread. Before v1.2 hardening only ``save`` took
``_lock``; unlocked concurrent reads came back as "no active federation
contract" for a contracted org (a spurious BLOCK), as ANOTHER org's contract
(whose scopes and data classes then decide the crossing), or as decode
errors.

This test drives 8 threads through the public methods in phases (one per
read query, every thread running it with a contract re-save mixed in, then
one mixed phase) and counts exceptions and wrong answers. It fails every time
on a copy of the store with the lock removed from the reads, and on copies
with the lock removed from any ONE read. Bounded: fixed thread and iteration
counts, and ONE 60 s join budget per phase (not 60 s per thread) that turns a
deadlock into a failure.
"""

from __future__ import annotations

import threading
import time
from collections import Counter

from federation_broker.engine import ContractStore, FederationContract

THREADS = 8
ITERS = 150  # per thread, per phase
WRITE_EVERY = 40  # one write in every 40 ops of a read phase
ORGS = 40


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


def _contract(i: int, ref: str) -> FederationContract:
    return FederationContract(
        contract_id=f"c-{i}", counterparty_org=f"Org {i}",
        allowed_scopes=[f"scope-{i}"], allowed_data_classes=[f"dc-{i}"],
        contract_ref=ref,
    )


def _mismatch(c: FederationContract, expect: int | None = None) -> str | None:
    try:
        i = int(c.contract_id.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return f"unknown_contract_id: {c.contract_id}"
    if expect is not None and i != expect:
        return f"wrong_row: asked Org {expect} got {c.contract_id}"
    if (c.counterparty_org, c.allowed_scopes, c.allowed_data_classes, c.active) != (
        f"Org {i}", [f"scope-{i}"], [f"dc-{i}"], True
    ):
        return f"mixed_row: {c.contract_id} {c.counterparty_org} {c.allowed_scopes}"
    return None


def test_concurrent_reads_and_writes_return_the_right_contract(tmp_path):
    store = ContractStore(tmp_path / "contracts.sqlite3")
    for i in range(ORGS):
        store.save(_contract(i, f"ref-{i}"))

    def op_for_org(k, n):
        i = (k * 7 + n) % ORGS
        c = store.for_org(f"Org {i}")
        if c is None:
            return f"spurious_no_contract: Org {i}"
        return _mismatch(c, i)

    def op_list(k, n):
        contracts = store.list()
        if len(contracts) != ORGS:
            return f"list_wrong_count: {len(contracts)}"
        return next((p for p in map(_mismatch, contracts) if p), None)

    def op_save(k, n):
        i = (k * 3 + n) % ORGS
        store.save(_contract(i, f"ref-{i}-{k}-{n}"))  # same identity, new ref
        return None

    # One phase per read query, so each races copies of ITSELF (the sharpest
    # interleaving) with writes mixed in; then one mixed phase.
    phases = [[read] * (WRITE_EVERY - 1) + [op_save] for read in (op_for_org, op_list)]
    phases.append([op_for_org, op_list, op_for_org, op_for_org] * 5 + [op_save])

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
        assert len(final) == ORGS and not any(map(_mismatch, final))
    finally:
        if not hung:  # a deadlocked worker still holds the lock close() needs
            store.close()
