"""GovernorStore under concurrent reads and writes.

The store holds ONE sqlite3 connection (``check_same_thread=False``) shared by
every FastAPI request thread. Before v1.2 hardening only writes took
``_lock``; unlocked concurrent reads came back as "no cap configured" and
"no policy" for agents that had both, as an empty escalation queue, as
another agent's cap, as spend totals mixed across agents, or as decode
errors — every one of them an input to the OK/ESCALATE/BLOCK decision.

This test drives 8 threads through the public methods in phases: one phase
per read method (every thread calling it, a spend or usage write mixed in),
one phase of concurrent resolves, and one mixed phase. It counts exceptions
and wrong answers. Each agent spends in its own unit (1000 + i), so totals
mixed from another agent are not multiples of it.

Resolves: at its n-th iteration every thread resolves the SAME open
escalation ``race-n`` under its own name. The first resolver wins: exactly
one call per escalation may report that it resolved it, and it must carry
that call's own name; every other call must return that winner's row; and a
late resolve afterwards must still read the winner (the stored
``resolved_by`` never changes after the first). The returned row is right
only while the read-back shares the UPDATE's lock hold. It fails every time
on a copy of the store with the lock removed from the reads, and on copies
with the lock removed from any ONE read. Bounded: fixed thread and iteration
counts, ONE 60 s join budget per phase that turns a deadlock into a failure.
"""

from __future__ import annotations

import threading
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone

from spend_governor.core import Escalation, GovernorStore, SpendCapConfig
from spend_governor.usage import UsagePolicy, UsageRecord

THREADS = 8
ITERS = 120  # per thread, per phase
WRITE_EVERY = 40  # one write in every 40 ops of a read phase
# open escalations race-0.., each resolved by every thread. 200, not 30: a
# read-back fetched after the lock is released showed up 17-29 times per run
# at 200 (5 of 5 runs), against as few as 4 at 30.
RESOLVE_ITERS = 200
AGENTS = 10
EPOCH = "1970-01-01T00:00:00+00:00"


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


def _unit(i: int) -> int:
    return 1000 + i


def test_concurrent_reads_and_writes_return_the_right_agent_state(tmp_path):
    store = GovernorStore(tmp_path / "spend.sqlite3")
    ts = datetime.now(timezone.utc).isoformat()
    for i in range(AGENTS):
        agent = f"agent-{i}"
        store.set_cap(SpendCapConfig(agent_id=agent, limit_cents=_unit(i), period="total"))
        store.set_policy(UsagePolicy(agent_id=agent, allowed_models=[f"model-{i}"],
                                     token_rate_limit=_unit(i)))
        for kind in ("cents", "tokens"):  # two open escalations per agent
            store.add_escalation(Escalation(
                escalation_id=f"esc-{i}-{kind}", agent_id=agent, ts=ts, kind=kind,
                spent=i, limit=_unit(i), pct=80))
        store.add_escalation(Escalation(  # one already-resolved escalation
            escalation_id=f"esc-{i}-actions", agent_id=agent, ts=ts, kind="actions",
            spent=i, limit=_unit(i), pct=80, resolved=True, resolved_by="setup"))
        store.record(agent, _unit(i), 0, 1, None, datetime.now(timezone.utc))
    for n in range(RESOLVE_ITERS):  # open, one per racer agent, resolved in the race
        store.add_escalation(Escalation(
            escalation_id=f"race-{n}", agent_id=f"racer-{n}", ts=ts, kind="cents",
            spent=n, limit=_unit(n), pct=80))

    def pick(k, n, mult):
        i = (k * mult + n) % AGENTS
        return i, f"agent-{i}"

    def op_get_cap(k, n):
        i, agent = pick(k, n, 7)
        cap = store.get_cap(agent)
        if cap is None:
            return f"cap_spurious_none: {agent}"
        if (cap.agent_id, cap.limit_cents) != (agent, _unit(i)):
            return f"cap_wrong_row: {agent} got {cap.agent_id} {cap.limit_cents}"
        return None

    def op_get_policy(k, n):
        i, agent = pick(k, n, 5)
        policy = store.get_policy(agent)
        if policy is None:
            return f"policy_spurious_none: {agent}"
        if (policy.agent_id, policy.allowed_models) != (agent, [f"model-{i}"]):
            return f"policy_wrong_row: {agent} got {policy.agent_id} {policy.allowed_models}"
        return None

    def op_totals(k, n):
        i, agent = pick(k, n, 11)
        cents, tokens, actions = store.totals_since(agent, EPOCH)
        if actions < 1 or tokens != 0 or cents != actions * _unit(i):
            return f"totals_mixed: {agent} cents={cents} tokens={tokens} actions={actions}"
        return None

    def op_window(k, n):
        i, agent = pick(k, n, 13)
        window = store.window_tokens(agent, EPOCH)
        if window % _unit(i):
            return f"window_tokens_mixed: {agent} {window}"
        return None

    def op_usage_totals(k, n):
        i, agent = pick(k, n, 13)
        tin, tout, cost, rows = store.usage_totals_since(agent, EPOCH)
        if tin % _unit(i) or tout or cost != tin * 10:
            return f"usage_totals_mixed: {agent} in={tin} out={tout} cost={cost}"
        if any(r["model"] != f"model-{i}" for r in rows):
            return f"usage_wrong_model: {agent} {[r['model'] for r in rows]}"
        return None

    def op_open_escalations(k, n):
        i, agent = pick(k, n, 17)
        escs = store.open_escalations(agent)
        if len(escs) != 2 or any(e.agent_id != agent or e.resolved for e in escs):
            return f"open_escalations_wrong: {agent} {[(e.escalation_id, e.resolved) for e in escs]}"
        return None

    def op_has_open(k, n):
        i, agent = pick(k, n, 17)
        if not store.has_open_escalation(agent, "cents"):
            return f"has_open_false_negative: {agent}"
        if store.has_open_escalation(agent, "actions"):
            return f"has_open_false_positive: {agent}"
        return None

    def op_spend(k, n):
        i, agent = pick(k, n, 3)
        store.record(agent, _unit(i), 0, 1, None, datetime.now(timezone.utc))
        return None

    def op_usage(k, n):
        i, agent = pick(k, n, 19)
        store.record_usage(UsageRecord(
            event_id=str(uuid.uuid4()), agent_id=agent,
            ts=datetime.now(timezone.utc).isoformat(), model=f"model-{i}",
            input_tokens=_unit(i), output_tokens=0, cost_units=_unit(i) * 10))
        return None

    resolutions: list[tuple[int, str | None, bool]] = []  # (n, returned resolver, flipped)
    resolutions_guard = threading.Lock()

    def op_resolve(k, n):  # write + read-back in one public call
        target = f"race-{n}"  # every thread resolves race-n at its n-th iteration
        try:
            esc, resolved_now = store.resolve_escalation_once(target, f"human-{k}")
        except KeyError:
            return f"resolve_spurious_keyerror: {target}"
        if (esc.escalation_id, esc.agent_id, esc.resolved) != (target, f"racer-{n}", True):
            return (f"resolve_wrong_row: {target} got {esc.escalation_id} "
                    f"{esc.agent_id} resolved={esc.resolved}")
        if resolved_now and esc.resolved_by != f"human-{k}":
            return f"resolve_winner_returned_other_resolver: human-{k} got {esc.resolved_by}"
        if esc.resolved_by not in {f"human-{j}" for j in range(THREADS)}:
            return f"resolve_resolver_not_a_caller: {target} got {esc.resolved_by}"
        with resolutions_guard:
            resolutions.append((n, esc.resolved_by, resolved_now))
        return None

    def first_resolver_won() -> Counter[str]:
        """Per race-n: exactly one call flipped it, every call returned the
        winner, and a late resolve by someone else still reads the winner."""
        found: Counter[str] = Counter()
        calls: defaultdict[int, list[tuple[str | None, bool]]] = defaultdict(list)
        for n, who, flipped in resolutions:
            calls[n].append((who, flipped))
        for n in range(RESOLVE_ITERS):
            winners = [who for who, flipped in calls[n] if flipped]
            if len(winners) != 1:
                found["resolve_not_exactly_one_winner"] += 1
            elif any(who != winners[0] for who, _ in calls[n]):
                found["resolve_returned_a_non_winner"] += 1
            late = store.resolve_escalation(f"race-{n}", "late-resolver")
            if len(winners) == 1 and late.resolved_by != winners[0]:
                found["resolve_stored_resolver_changed"] += 1
        return found

    # One phase per read method, so every read races copies of ITSELF (the
    # sharpest interleaving) with writes mixed in; then a phase of colliding
    # resolves (write + read-back); then one mixed phase.
    reads = [op_get_cap, op_totals, op_get_policy, op_window, op_usage_totals,
             op_open_escalations, op_has_open]
    writes = [op_spend, op_usage]
    phases = [([read] * (WRITE_EVERY - 1) + [writes[j % 2]], ITERS)
              for j, read in enumerate(reads)]
    phases.append(([op_resolve], RESOLVE_ITERS))
    phases.append((reads * 3 + [op_spend, op_usage], ITERS))

    anomalies: Counter[str] = Counter()
    examples: list[str] = []
    hung = 0
    for ops, iters in phases:
        found, seen, hung = _hammer(ops, iters=iters)
        anomalies.update(found)
        examples.extend(seen[: 5 - len(examples)])
        if hung:
            break
    if not hung:
        anomalies.update(first_resolver_won())

    try:
        assert hung == 0, f"{hung} worker thread(s) still running after 60 s: deadlock"
        total = THREADS * sum(iters for _, iters in phases)
        assert not anomalies, (
            f"{sum(anomalies.values())} anomalies in {total} concurrent store "
            f"calls: {dict(anomalies)}; e.g. {examples}"
        )
    finally:
        if not hung:  # a deadlocked worker still holds the lock close() needs
            store.close()
