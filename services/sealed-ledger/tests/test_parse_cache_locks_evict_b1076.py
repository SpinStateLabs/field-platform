"""B-1076-LOCK-TESTS: the T7 parse cache's lock and memory cap (PR 1076, ``LedgerStore._parsed`` /
``_remember`` / ``_verified``, guarded by ``_cache_lock``).

Locks. Reads are lock-free (no L0/L1); ``_cache_lock`` is the only thing keeping the cache dict and the
verify tuple consistent between concurrent readers. A lock-removal mutant changes no output under the GIL, so
a result comparison cannot kill it. These tests instead force the interleaving: a probe wraps the cache
structures, a thread "A" parks INSIDE the critical section on a ``threading.Event``, and a second thread "B"
enters the same cache. With the lock, B cannot touch the cache while A is parked; without it, B's access is
observed during A's pause. Two checks per site, no sleep as synchronisation:

* ``_cache_lock.locked()`` is asserted while A is parked (fully deterministic);
* ``overlap`` is false: B made no cache access while A was inside (B's access releases A at once; the
  1 s ``Event.wait`` timeout only bounds how long the locked code waits to prove B stayed out).

Eviction. ``_remember`` is exercised with exact byte sizes against a patched ``PARSE_CACHE_MAX_BYTES``:
oldest-first eviction, live bytes <= cap after every call, a segment larger than the cap is not cached (and
drops its stale entry), the cap / cap+1 boundary, the newest entry is never the one evicted, and the verify
cache honours the same cap."""
from __future__ import annotations

import random
import threading
from pathlib import Path

import pytest

import sealed_ledger.store as store_mod
from field_core.ledger import LedgerEvent
from sealed_ledger.store import LedgerStore

from ledger_c2_support import rotate

JOIN_S = 30.0
PAUSE_WAIT_S = 1.0  # upper bound the LOCKED code waits to prove the other thread stayed out


def _dump(events) -> list[dict]:
    return [e.model_dump(mode="json") for e in events]


class Probe:
    """Records, for each cache access, the thread, the op and whether ``_cache_lock`` was held. Thread "A" is
    parked inside the critical section on its first hit of ``pause_op``; any access by another thread while A
    is parked is an ``overlap``."""

    def __init__(self, store: LedgerStore):
        self.store = store
        self.log: list[tuple[str, str, bool]] = []
        self.pause_op: str | None = None
        self.pause_done = False
        self.parked = False
        self.overlap = False
        self.locked_while_parked: bool | None = None
        self.inside = threading.Event()
        self.other_touched = threading.Event()

    def arm(self, op: str) -> None:
        self.pause_op, self.pause_done = op, False

    def hit(self, op: str) -> None:
        me = threading.current_thread().name
        self.log.append((me, op, self.store._cache_lock.locked()))
        if self.parked and me != "A":
            self.overlap = True
            self.other_touched.set()
        elif me == "A" and op == self.pause_op and not self.pause_done:
            self.pause_done = True
            self.locked_while_parked = self.store._cache_lock.locked()
            self.parked = True
            self.inside.set()
            self.other_touched.wait(PAUSE_WAIT_S)
            self.parked = False

    def ops(self, op: str) -> list[tuple[str, str, bool]]:
        return [row for row in self.log if row[1] == op]


class WatchedDict(dict):
    def __init__(self, probe: Probe, data):
        super().__init__(data)
        self._probe = probe

    def get(self, *a):
        self._probe.hit("get")
        return super().get(*a)

    def pop(self, *a):
        self._probe.hit("pop")
        return super().pop(*a)

    def __setitem__(self, k, v):
        self._probe.hit("set")
        super().__setitem__(k, v)

    def values(self):
        self._probe.hit("values")
        return super().values()

    def __iter__(self):
        self._probe.hit("iter")
        return super().__iter__()


class WatchedStore(LedgerStore):
    """A store whose ``_verify_cache`` read and write are observable."""

    probe: Probe | None = None
    _vc = None

    @property
    def _verify_cache(self):
        if self.probe is not None:
            self.probe.hit("vget")
        return self._vc

    @_verify_cache.setter
    def _verify_cache(self, value):
        if self.probe is not None:
            self.probe.hit("vset")
        self._vc = value


def _seed(tmp_path: Path, n: int = 20, cls=LedgerStore) -> LedgerStore:
    store = cls(tmp_path / "events.jsonl")
    for i in range(n):
        store.append("gateway.request", {"seq": i}, f"agent-{i % 3}")
    return store


def _instrument(store: LedgerStore) -> Probe:
    probe = Probe(store)
    store._parse_cache = WatchedDict(probe, store._parse_cache)
    if isinstance(store, WatchedStore):
        store.probe = probe
    return probe


def _thread(name: str, fn, errors: list) -> threading.Thread:
    def run():
        try:
            fn()
        except BaseException as exc:  # surfaced by the test
            errors.append(exc)

    return threading.Thread(target=run, name=name, daemon=True)


def _exclusion(store: LedgerStore, probe: Probe, op: str, run_a, run_b) -> None:
    """A parks inside the critical section at ``op``; B enters the same cache; neither may overlap."""
    errors: list = []
    probe.arm(op)
    a = _thread("A", run_a, errors)
    a.start()
    assert probe.inside.wait(JOIN_S), f"thread A never reached the cache op {op!r}"
    assert probe.locked_while_parked is True, f"_cache_lock not held while a thread is inside {op!r}"
    b = _thread("B", run_b, errors)
    b.start()
    a.join(JOIN_S)
    b.join(JOIN_S)
    assert not a.is_alive() and not b.is_alive()
    assert not errors, errors
    assert probe.overlap is False, f"a second thread used the cache while another was inside {op!r}"
    assert not store._cache_lock.locked()


# ------------------------------------------------------------------ lock sites


def test_every_parse_cache_access_holds_the_cache_lock(tmp_path):
    """Kills the lock removal in ``_parsed`` (the lookup) and ``_remember`` (pop / insert / total / evict)."""
    store = _seed(tmp_path)
    probe = _instrument(store)
    store.events()  # miss: lookup then remember
    store.append("gateway.request", {"seq": 99}, "agent-1")
    store.events()  # extension: lookup then remember
    store.verify()
    for op in ("get", "pop", "set", "values", "iter"):
        rows = probe.ops(op)
        assert rows, f"the read path never performed cache op {op!r}"
        assert all(locked for _t, _o, locked in rows), f"{op!r} ran without _cache_lock: {rows}"


def test_the_cache_lookup_in_parsed_excludes_a_concurrent_reader(tmp_path):
    store = _seed(tmp_path)
    probe = _instrument(store)
    _exclusion(store, probe, "get", store.events, store.events)


def test_remember_excludes_a_concurrent_remember(tmp_path, monkeypatch):
    store = _seed(tmp_path, n=2)
    monkeypatch.setattr(store_mod, "PARSE_CACHE_MAX_BYTES", 1000)
    store._parse_cache.clear()
    probe = _instrument(store)
    p, q = Path("seg-p"), Path("seg-q")
    _exclusion(store, probe, "values",
               lambda: store._remember(p, b"x" * 400, ()),
               lambda: store._remember(q, b"y" * 400, ()))
    assert set(store._parse_cache) == {p, q}


def test_the_verify_cache_read_excludes_a_concurrent_verify(tmp_path):
    store = _seed(tmp_path, cls=WatchedStore)
    probe = _instrument(store)
    _exclusion(store, probe, "vget", store.verify, store.verify)


def test_the_verify_cache_write_excludes_a_concurrent_verify(tmp_path):
    store = _seed(tmp_path, cls=WatchedStore)
    probe = _instrument(store)
    _exclusion(store, probe, "vset", store.verify, store.verify)
    assert store.verify().ok


def test_the_verify_cache_is_read_and_written_under_the_lock(tmp_path):
    store = _seed(tmp_path, cls=WatchedStore)
    probe = _instrument(store)
    store.verify()
    store.verify()
    reads, writes = probe.ops("vget"), probe.ops("vset")
    assert reads and writes
    assert all(locked for _t, _o, locked in reads + writes), (reads, writes)


# ------------------------------------------- concurrent events() + append, forced interleave


def test_an_append_landing_while_a_reader_is_inside_the_cache_does_not_tear_that_read(tmp_path):
    """A's events() is parked inside the cache (after its snapshot); B appends then reads. A keeps its
    consistent pre-append snapshot, B sees the append, the next read sees both, and every answer equals a
    fresh store's. The append path takes no cache lock, so B's append runs while A holds it."""
    store = _seed(tmp_path, n=12)
    probe = _instrument(store)
    probe.arm("set")
    seen: dict[str, list] = {}
    errors: list = []
    store._parse_cache.clear()

    a = _thread("A", lambda: seen.__setitem__("a", _dump(store.events())), errors)
    a.start()
    assert probe.inside.wait(JOIN_S)

    def writer_then_reader():
        store.append("gateway.request", {"seq": 1000}, "agent-9")
        probe.other_touched.set()  # the append needs no cache lock: release A explicitly
        seen["b"] = _dump(store.events())

    b = _thread("B", writer_then_reader, errors)
    b.start()
    a.join(JOIN_S)
    b.join(JOIN_S)
    assert not errors, errors
    assert len(seen["a"]) == 12 and len(seen["b"]) == 13
    assert seen["b"][:12] == seen["a"]
    assert _dump(store.events()) == seen["b"] == _dump(LedgerStore(store.path).events())
    assert store.verify().ok and store.verify().length == 13


def test_concurrent_readers_and_an_appender_always_see_a_consistent_prefix(tmp_path):
    """Barrier-started stress run (real code must pass on every run): readers' answers are always a
    contiguous prefix of the final ledger and verify() is never broken. Not a lock-mutant killer under the
    GIL (see the forced-interleave tests above); it pins the end-to-end contract."""
    store = _seed(tmp_path, n=10)
    appends, readers = 40, 4
    barrier = threading.Barrier(readers + 1)
    errors: list = []
    answers: list[list[dict]] = []
    verdicts: list = []

    def appender():
        barrier.wait(JOIN_S)
        for i in range(appends):
            store.append("gateway.request", {"seq": 100 + i}, "agent-w")

    def reader():
        barrier.wait(JOIN_S)
        for _ in range(25):
            answers.append(_dump(store.events()))
            verdicts.append(store.verify())

    ts = [_thread("W", appender, errors)] + [_thread(f"R{k}", reader, errors) for k in range(readers)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(JOIN_S * 4)
    assert not errors and not any(t.is_alive() for t in ts), errors
    final = _dump(store.events())
    assert len(final) == 10 + appends
    for ans in answers:
        assert ans == final[: len(ans)]
    assert all(v.ok for v in verdicts)
    assert _dump(LedgerStore(store.path).events()) == final


# ------------------------------------------------------------------- eviction


@pytest.fixture
def cap(monkeypatch):
    def set_cap(n: int) -> None:
        monkeypatch.setattr(store_mod, "PARSE_CACHE_MAX_BYTES", n)

    return set_cap


def _empty_store(tmp_path: Path) -> LedgerStore:
    store = LedgerStore(tmp_path / "events.jsonl")
    store._parse_cache.clear()
    return store


def _live(store: LedgerStore) -> int:
    return sum(len(raw) for raw, _ev, _ro in store._parse_cache.values())


def _blob(n: int, ch: bytes = b"x") -> bytes:
    return ch * n


def _names(store: LedgerStore) -> list[str]:
    return [p.name for p in store._parse_cache]


def test_eviction_is_oldest_first(tmp_path, cap):
    cap(100)
    s = _empty_store(tmp_path)
    for name in ("a", "b", "c"):
        s._remember(Path(name), _blob(40), ())
    assert _names(s) == ["b", "c"]  # 120 > 100: only the oldest goes
    s._remember(Path("d"), _blob(40), ())
    assert _names(s) == ["c", "d"]
    assert _live(s) == 80


def test_eviction_keeps_going_until_the_total_fits(tmp_path, cap):
    cap(100)
    s = _empty_store(tmp_path)
    for name in ("a", "b", "c"):
        s._remember(Path(name), _blob(30), ())
    s._remember(Path("d"), _blob(100), ())  # 190 -> must drop a, b, c
    assert _names(s) == ["d"] and _live(s) == 100


def test_a_refreshed_path_becomes_the_newest(tmp_path, cap):
    cap(100)
    s = _empty_store(tmp_path)
    s._remember(Path("a"), _blob(40), ())
    s._remember(Path("b"), _blob(40), ())
    s._remember(Path("a"), _blob(45, b"y"), ())  # a is now newest; its old bytes are replaced, not added
    assert _names(s) == ["b", "a"] and _live(s) == 85
    s._remember(Path("c"), _blob(40), ())  # 125: b (now the oldest) goes, a stays
    assert _names(s) == ["a", "c"]


def test_live_bytes_never_exceed_the_cap_and_the_newest_survives(tmp_path, cap):
    rng = random.Random(1076)
    cap(500)
    s = _empty_store(tmp_path)
    for i in range(300):
        size = rng.randint(1, 700)
        path = Path(f"seg-{rng.randint(0, 6)}")
        s._remember(path, _blob(size), ())
        assert _live(s) <= 500, f"step {i}: {_live(s)} live bytes > cap"
        if size <= 500:
            assert path in s._parse_cache and len(s._parse_cache[path][0]) == size, f"step {i}"
        else:
            assert path not in s._parse_cache, f"step {i}: oversize segment cached"


def test_a_segment_larger_than_the_cap_is_not_cached_and_drops_its_stale_entry(tmp_path, cap):
    cap(100)
    s = _empty_store(tmp_path)
    s._remember(Path("a"), _blob(30), ())
    s._remember(Path("b"), _blob(40), ())
    s._remember(Path("b"), _blob(101), ())  # grew past the cap
    assert _names(s) == ["a"], "oversize b must neither be kept nor evict a, and its stale 40 bytes must go"
    assert _live(s) == 30


def test_the_cap_boundary_is_exact(tmp_path, cap):
    cap(100)
    s = _empty_store(tmp_path)
    s._remember(Path("a"), _blob(100), ())
    assert _names(s) == ["a"] and _live(s) == 100  # == cap: cached
    s._remember(Path("b"), _blob(101), ())
    assert _names(s) == ["a"]  # cap + 1: refused, nothing evicted


def test_a_total_equal_to_the_cap_evicts_nothing_and_one_more_byte_evicts_the_oldest(tmp_path, cap):
    cap(100)
    s = _empty_store(tmp_path)
    s._remember(Path("a"), _blob(60), ())
    s._remember(Path("b"), _blob(40), ())
    assert _names(s) == ["a", "b"] and _live(s) == 100  # total == cap: kept
    s._remember(Path("c"), _blob(1), ())
    assert _names(s) == ["b", "c"] and _live(s) == 41  # 101 > cap: a (oldest) goes, 60 freed


def test_eviction_never_drops_the_entry_it_was_called_for(tmp_path, cap):
    cap(100)
    s = _empty_store(tmp_path)
    s._remember(Path("a"), _blob(10), ())
    s._remember(Path("b"), _blob(10), ())
    events = ()
    s._remember(Path("c"), _blob(100), events)  # fills the cap alone: everything else goes, c stays
    assert _names(s) == ["c"] and s._parse_cache[Path("c")][:2] == (_blob(100), events)


def test_the_verify_cache_follows_the_same_cap_boundary(tmp_path, cap):
    store = _seed(tmp_path, n=8, cls=WatchedStore)
    total = sum(len(d) for d in store._take_snapshot(tolerant=True).raw if d is not None)
    cap(total)
    assert store.verify().ok
    assert store._vc is not None, "raw bytes == cap: the verification is cached"
    store._vc = None
    store._parse_cache.clear()
    cap(total - 1)
    assert store.verify().ok
    assert store._vc is None, "raw bytes == cap + 1: the verification must not be cached"
    assert not store._parse_cache, "and neither is the parse"


def test_reads_over_a_small_cap_stay_correct_and_bounded_across_segments(tmp_path, cap, monkeypatch):
    store = _seed(tmp_path, n=30)
    store.events()
    rotate(store)
    for i in range(3):
        store.append("gateway.request", {"seq": 500 + i}, "agent-1")
    fresh = _dump(LedgerStore(store.path).events())
    sizes = sorted(len(d) for d in store._take_snapshot().raw if d)
    biggest, both = sizes[-1], sum(sizes)
    assert len(sizes) == 2 and biggest < both

    cap(both - 1)  # cannot hold both live segments
    store._parse_cache.clear()
    for _ in range(3):
        assert _dump(store.events()) == fresh
        assert store.verify().ok
        assert 0 < _live(store) <= both - 1

    cap(both)  # holds both: a second read parses nothing
    store._parse_cache.clear()
    store.events()
    assert _live(store) == both and len(store._parse_cache) == 2
    calls = [0]
    original = LedgerEvent.model_validate

    def counting(obj, *a, **k):
        calls[0] += 1
        return original(obj, *a, **k)

    monkeypatch.setattr(LedgerEvent, "model_validate", counting)
    assert _dump(store.events()) == fresh
    assert calls[0] == 0
