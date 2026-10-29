"""C-373 (reviewer C-369 F-C369-1): the once-per-row warning memory is atomic and bounded.

`_cap_row_warned` (and `_policy_row_warned`) were plain module-level sets: the check and the add were two steps
with no lock, and the set grew by one key per distinct stored value for the life of the process. They are now a
`_WarnOnce`: `first(key)` is True for exactly one caller per remembered key, and the memory holds at most
`limit` keys (the oldest is forgotten, so a very old row can warn once more: a repeat line is harmless)."""

from __future__ import annotations

import logging
import threading
import time

import pytest

from spend_governor import core
from spend_governor.core import MAX_AMOUNT, GovernorStore, _WarnOnce

AGENT = "legacy-agent"
INT64_MAX = 2**63 - 1


def test_first_is_true_once_per_key():
    w = _WarnOnce()
    assert w.first(("a", 1)) is True
    assert w.first(("a", 1)) is False
    assert w.first(("a", 2)) is True
    assert w.first(("b", 1)) is True
    assert w.first(("a", 1)) is False


class _SlowDict(dict):
    """A membership test that yields: with a lock the two steps stay together, without one every thread passes
    the check before any of them adds (deterministic, where a real race needs luck)."""

    def __contains__(self, key):
        answer = super().__contains__(key)      # the answer is taken first, then the caller is held up
        time.sleep(0.02)
        return answer


def test_concurrent_callers_get_exactly_one_true():
    w = _WarnOnce()
    w._seen = _SlowDict()
    n = 16
    barrier = threading.Barrier(n)
    got: list[bool] = []

    def run():
        barrier.wait()
        got.append(w.first(("row", 1)))

    threads = [threading.Thread(target=run) for _ in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert got.count(True) == 1 and len(got) == n


def test_the_memory_is_bounded_and_forgets_the_oldest():
    w = _WarnOnce(limit=8)
    for i in range(100):
        assert w.first(("k", i)) is True
    assert len(w) == 8
    assert w.first(("k", 99)) is False       # the newest is remembered
    assert w.first(("k", 92)) is False       # the oldest still held (92..99)
    assert w.first(("k", 91)) is True        # one past the limit was forgotten
    assert len(w) == 8


def test_a_new_key_at_the_limit_is_remembered_not_evicted_at_once():
    w = _WarnOnce(limit=2)
    assert w.first("a") and w.first("b") and w.first("c")
    assert w.first("c") is False and w.first("b") is False
    assert w.first("a") is True


def test_the_default_limit_is_a_few_thousand_at_most():
    assert 0 < _WarnOnce()._limit <= 4096


def legacy_cap(store, agent=AGENT, limit=INT64_MAX):
    with store._lock, store._conn:
        store._conn.execute(
            "INSERT OR REPLACE INTO caps (agent_id, currency, limit_cents, token_limit, action_limit, period,"
            " escalate_at_pct, on_breach) VALUES (?, 'USD', ?, NULL, NULL, 'daily', 80, 'halt')", (agent, limit))


def legacy_policy(store, agent=AGENT):
    with store._lock, store._conn:
        store._conn.execute(
            "INSERT OR REPLACE INTO usage_policies (agent_id, allowed_models, token_rate_limit,"
            " rate_window_seconds) VALUES (?, '[]', ?, ?)", (agent, 100, 2 * 366 * 86400))


def _threads(fn, n=32):
    barrier = threading.Barrier(n)

    def run():
        barrier.wait()
        fn()

    ts = [threading.Thread(target=run) for _ in range(n)]
    [t.start() for t in ts]
    [t.join() for t in ts]


@pytest.mark.parametrize("trial", range(5))
def test_many_readers_of_one_legacy_cap_row_produce_one_warning(tmp_path, monkeypatch, caplog, trial):
    monkeypatch.setattr(core, "_cap_row_warned", _WarnOnce())
    store = GovernorStore(tmp_path / "spend.sqlite3")
    legacy_cap(store)
    with caplog.at_level(logging.WARNING, logger="spend_governor.core"):
        _threads(lambda: store.get_cap(AGENT))
    assert len([r for r in caplog.records if "cap row" in r.getMessage()]) == 1


@pytest.mark.parametrize("trial", range(5))
def test_many_readers_of_one_legacy_policy_row_produce_one_warning(tmp_path, monkeypatch, caplog, trial):
    monkeypatch.setattr(core, "_policy_row_warned", _WarnOnce())
    store = GovernorStore(tmp_path / "spend.sqlite3")
    legacy_policy(store)
    with caplog.at_level(logging.WARNING, logger="spend_governor.core"):
        _threads(lambda: store.get_policy(AGENT))
    assert len([r for r in caplog.records if "usage policy row" in r.getMessage()]) == 1


def test_the_cap_and_policy_memories_are_separate(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(core, "_cap_row_warned", _WarnOnce())
    monkeypatch.setattr(core, "_policy_row_warned", _WarnOnce())
    store = GovernorStore(tmp_path / "spend.sqlite3")
    legacy_cap(store)
    legacy_policy(store)
    with caplog.at_level(logging.WARNING, logger="spend_governor.core"):
        store.get_cap(AGENT)
        store.get_policy(AGENT)
        store.get_cap(AGENT)
        store.get_policy(AGENT)
    msgs = [r.getMessage() for r in caplog.records]
    assert len([m for m in msgs if "cap row" in m]) == 1 and len([m for m in msgs if "usage policy row" in m]) == 1


def test_a_stream_of_rewritten_rows_cannot_grow_the_memory_past_its_limit(tmp_path, monkeypatch):
    mem = _WarnOnce(limit=16)
    monkeypatch.setattr(core, "_cap_row_warned", mem)
    store = GovernorStore(tmp_path / "spend.sqlite3")
    for i in range(200):
        legacy_cap(store, limit=MAX_AMOUNT + 1 + i)
        store.get_cap(AGENT)
    assert len(mem) == 16
