"""Subprocess side of the C2 reader tests (``test_ledger_readers.py``).

Not a test module: run as ``python ledger_c2_harness.py <mode> ...``. Every
mode prints one ``JSON{...}`` line with its result. Ported from the C2 build
spec lab's judge harness (j_interleave, j_readers, j_twowriters, g5b, j_manysegs).
"""

from __future__ import annotations

import builtins
import io
import json
import os
import random
import shutil
import sys
import threading
import time
from pathlib import Path

import field_core.signing  # noqa: F401  (import cost outside any measured region)
from sealed_ledger import store as store_mod
from sealed_ledger.store import LedgerStore

INF = 10 ** 9
# Wall-clock bounds of the interleaving harness. They only bound how long a
# schedule may take on a loaded host: a reader that is merely slow is not a
# violation, so they are far above any normal schedule (seconds) and a genuine
# deadlock still shows as "stuck" / "writer gate timeout".
PARK_TIMEOUT_S = 120.0
READER_JOIN_S = 180.0


def emit(obj) -> None:
    print("JSON" + json.dumps(obj), flush=True)


def _key(keyfile: str) -> str:
    return Path(keyfile).read_text(encoding="ascii")


def _rotate(store: LedgerStore, key: str):
    return store.rotate(private_key_pem=key, operator="harness", reason="harness")


class Tally:
    def __init__(self):
        self.lock = threading.Lock()
        self.c: dict[str, int] = {}
        self.samples: dict[str, list[str]] = {}

    def add(self, k: str, sample: str | None = None):
        with self.lock:
            self.c[k] = self.c.get(k, 0) + 1
            if sample is not None and len(self.samples.setdefault(k, [])) < 5:
                self.samples[k].append(sample[:240])


# ------------------------------------------------------------ interleavings
#
# The WRITER thread runs a real rotate(). Before every mutating filesystem call
# it parks at a gate. The READER thread runs one real read; before every
# observation (stat, open-for-read, the Windows share-delete opener) the
# scheduler may advance the writer. Schedule (a, i, j): before observation i
# the writer runs its first a mutating calls; before observation j it runs to
# completion. Pass: ok/events/health => N or N+1 events with the prefix intact.


class Sched:
    def __init__(self):
        self.cv = threading.Condition()
        self.allowed = 0
        self.arrived = 0
        self.done = False
        self.writer = None
        self.reader = None
        self.obs = 0
        self.plan: dict[int, int] = {}
        self.active = False

    def wgate(self):
        with self.cv:
            self.arrived += 1
            self.cv.notify_all()
            while self.arrived > self.allowed:
                if not self.cv.wait(PARK_TIMEOUT_S):
                    raise RuntimeError("writer gate timeout")

    def wdone(self):
        with self.cv:
            self.done = True
            self.cv.notify_all()

    def advance_to(self, a: int):
        with self.cv:
            self.allowed = max(self.allowed, a)
            self.cv.notify_all()
            t_end = time.monotonic() + PARK_TIMEOUT_S
            while not self.done and self.arrived <= self.allowed:
                if not self.cv.wait(max(0.01, t_end - time.monotonic())) and time.monotonic() > t_end:
                    raise RuntimeError(f"writer did not park (allowed {self.allowed}, arrived {self.arrived})")

    def robs(self):
        self.obs += 1
        a = self.plan.get(self.obs)
        if a is not None:
            self.advance_to(a)


S = Sched()


def install_scheduler(split_layout_and_validation: bool) -> None:
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC

    def gate_w():
        if S.active and threading.current_thread() is S.writer:
            S.wgate()

    def gate_r():
        if S.active and threading.current_thread() is S.reader:
            S.robs()

    for attr in ("write", "fsync", "rename", "replace", "ftruncate", "truncate", "unlink", "remove"):
        orig = getattr(os, attr)

        def mut(*a, _o=orig, **k):
            gate_w()
            return _o(*a, **k)

        setattr(os, attr, mut)
    orig_stat = os.stat

    def stat_w(*a, **k):
        gate_r()
        return orig_stat(*a, **k)

    os.stat = stat_w
    for attr in ("exists", "isfile", "isdir", "lexists"):
        orig_p = getattr(os.path, attr)

        def pw(*a, _o=orig_p, **k):
            gate_r()
            return _o(*a, **k)

        setattr(os.path, attr, pw)
    orig_osopen = os.open

    def osopen_w(p, flags, *a, **k):
        (gate_w if flags & write_flags else gate_r)()
        return orig_osopen(p, flags, *a, **k)

    os.open = osopen_w
    orig_open = builtins.open

    def open_w(*a, **k):
        mode = a[1] if len(a) > 1 else k.get("mode", "r")
        if not isinstance(a[0], int):
            if isinstance(mode, str) and any(c in mode for c in "wax+"):
                gate_w()
            else:
                gate_r()
        return orig_open(*a, **k)

    builtins.open = open_w
    io.open = open_w
    if os.name == "nt":  # on POSIX open_shared IS builtins.open (already a scheduling point)
        orig_shared = store_mod.open_shared

        def shared_w(p):
            gate_r()
            return orig_shared(p)

        store_mod.open_shared = shared_w
    if split_layout_and_validation:
        # NEGATIVE CONTROL: decide the layout from its OWN stats instead of the
        # memoised observations the snapshot re-validates (the defect the
        # build spec's trap 1 describes). The checker must catch it.
        orig_resolve = store_mod.resolve_layout

        def split(open_path, js, exists=None):
            return orig_resolve(open_path, js, store_mod.exists_strict)

        store_mod.resolve_layout = split


def build_template(d: Path, key: str, state: str) -> list[str]:
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    st = LedgerStore(d / "events.jsonl")
    for i in range(5):
        st.append("seed", {"i": i}, agent_id="a")
    if state == "second":
        _rotate(st, key)
        st.append("x", {}, agent_id="a")
        st.append("x", {}, agent_id="a")
    return [e.hash for e in st.events()]


def _reader_op(op: str, p: Path, long_st: LedgerStore, wst: LedgerStore):
    if op == "verify_fresh":
        v = LedgerStore(p).verify()
        return "verify", {"ok": v.ok, "length": v.length, "reason": v.reason}
    if op == "events_long":
        return "events", [e.hash for e in long_st.events()]
    if op == "health_fresh":
        return "health", LedgerStore(p).health_info()["event_count"]
    if op == "health_writer":
        return "health", wst.health_info()["event_count"]
    if op == "verify_writer":
        v = wst.verify()
        return "verify", {"ok": v.ok, "length": v.length, "reason": v.reason}
    raise ValueError(op)


def _classify(kind, val, pre, n):
    if kind == "verify":
        if not val["ok"]:
            return ("busy" if "busy" in (val["reason"] or "") else "false_break"), val["reason"]
        if val["length"] not in (n, n + 1):
            return "VIOLATION", f"ok length {val['length']} (pre {n})"
        return "pass", None
    if kind == "events":
        if len(val) not in (n, n + 1) or val[:n] != pre:
            return "VIOLATION", f"events len {len(val)} (pre {n}) prefix_ok={val[:n] == pre}"
        return "pass", None
    if val not in (n, n + 1):
        return ("VIOLATION" if val < n else "over"), f"health {val} (pre {n})"
    return "pass", None


def interleave_worker(work: Path, state: str, op: str, shard: int, nshards: int, keyfile: str,
                      control: bool) -> None:
    key = _key(keyfile)
    tpl = work / f"tpl_{state}"
    pre = json.loads((work / f"tpl_{state}.json").read_text())
    n = len(pre)
    install_scheduler(split_layout_and_validation=control)
    # As in steps_worker: the reader's 5 s busy deadline is a latency bound, not
    # a correctness one; a starved reader answered "busy" (and a join that gave
    # up after 8 s) on a loaded shared host.
    LedgerStore.SNAPSHOT_TIMEOUT_S = 120.0
    counts: dict[str, int] = {}
    samples: list = []
    seq = [0]

    def one(a: int, i: int, j: int, probe: bool = False):
        seq[0] += 1
        shutil.rmtree(work / f"s_{state}_{op}_{shard}_{seq[0] - 1}", ignore_errors=True)
        d = work / f"s_{state}_{op}_{shard}_{seq[0]}"
        shutil.copytree(tpl, d)
        p = d / "events.jsonl"
        wst = LedgerStore(p)
        long_st = LedgerStore(p)
        S.__init__()
        res: dict = {}

        def wrun():
            try:
                _rotate(wst, key)
            except Exception as exc:  # noqa: BLE001
                res["werr"] = f"{type(exc).__name__}: {exc}"
            finally:
                S.wdone()

        def rrun():
            try:
                res["r"] = _reader_op(op, p, long_st, wst)
            except Exception as exc:  # noqa: BLE001
                res["rerr"] = f"{type(exc).__name__}: {exc}"[:200]

        S.plan = {} if probe else ({i: INF} if a >= INF else {i: a, j: INF})
        wt = threading.Thread(target=wrun)
        rt = threading.Thread(target=rrun)
        S.writer, S.reader = wt, rt
        S.active = True
        if probe:
            S.allowed = INF
        wt.start()
        if not probe:
            S.advance_to(0)
        else:
            wt.join(30)
        rt.start()
        rt.join(READER_JOIN_S)
        if rt.is_alive():
            S.active = False
            try:
                S.advance_to(INF)
            except RuntimeError:
                pass
            rt.join(30)
            return "stuck", f"a={a} i={i} j={j}", S.obs, S.arrived
        S.advance_to(INF)
        wt.join(30)
        S.active = False
        if "rerr" in res:
            return "exception", res["rerr"], S.obs, S.arrived
        if "werr" in res:
            return "writer_error", res["werr"], S.obs, S.arrived
        kind, val = res["r"]
        c, why = _classify(kind, val, pre, n)
        return c, why, S.obs, S.arrived

    S.__init__()
    _, _, _, w_calls = one(0, INF, INF, probe=True)
    _, _, r_obs, _ = one(0, INF + 1, INF + 1)
    schedules = [(INF, i, i) for i in range(1, r_obs + 2)]
    for a in range(1, w_calls):
        for i in range(1, r_obs + 1):
            for j in range(i + 1, r_obs + 2):
                schedules.append((a, i, j))
    t0 = time.time()
    for idx, (a, i, j) in enumerate(schedules):
        if idx % nshards != shard:
            continue
        c, why, _, _ = one(a, i, j)
        counts[c] = counts.get(c, 0) + 1
        if c not in ("pass", "over") and len(samples) < 8:
            samples.append({"a": a, "i": i, "j": j, "class": c, "why": why})
    shutil.rmtree(work / f"s_{state}_{op}_{shard}_{seq[0]}", ignore_errors=True)
    emit({"state": state, "op": op, "shard": shard, "W": w_calls, "R": r_obs, "counts": counts,
          "samples": samples, "seconds": round(time.time() - t0, 1)})


# ------------------------------------------------- step placement (multi-park)
#
# The single-park checker above advances the writer once, then runs it to
# completion; completion always includes the journal commit, which forces a
# snapshot retry, so a race BETWEEN layout decision and validation inside one
# snapshot is outside its schedule space. This checker places each rotation
# step independently: positions p1 <= p2 <= p3 <= p4 over the reader's M
# observations (0 = before the first, M = after the read), and runs the step
# inline, in the reader's thread, just before that observation.


class _Inline:
    def __init__(self):
        self.active = False
        self.obs = 0
        self.at: dict[int, list] = {}
        self.running = False

    def observe(self):
        if not self.active or self.running:
            return
        steps = self.at.pop(self.obs, [])
        self.obs += 1
        if steps:
            self.running = True
            try:
                for step in steps:
                    step()
            finally:
                self.running = False


INLINE = _Inline()


def install_inline(split_layout_and_validation: bool) -> None:
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
    orig_stat = os.stat

    def stat_w(*a, **k):
        INLINE.observe()
        return orig_stat(*a, **k)

    os.stat = stat_w
    orig_osopen = os.open

    def osopen_w(p, flags, *a, **k):
        if not flags & write_flags:
            INLINE.observe()
        return orig_osopen(p, flags, *a, **k)

    os.open = osopen_w
    orig_open = builtins.open

    def open_w(*a, **k):
        mode = a[1] if len(a) > 1 else k.get("mode", "r")
        if not isinstance(a[0], int) and not (isinstance(mode, str) and any(c in mode for c in "wax+")):
            INLINE.observe()
        return orig_open(*a, **k)

    builtins.open = open_w
    io.open = open_w
    if os.name == "nt":
        orig_shared = store_mod.open_shared

        def shared_w(p):
            INLINE.observe()
            return orig_shared(p)

        store_mod.open_shared = shared_w
    if split_layout_and_validation:
        orig_resolve = store_mod.resolve_layout

        def split(open_path, js, exists=None):
            return orig_resolve(open_path, js, store_mod.exists_strict)

        store_mod.resolve_layout = split


def steps_worker(work: Path, state: str, op: str, shard: int, nshards: int, keyfile: str,
                 control: bool) -> None:
    import itertools

    key = _key(keyfile)
    tpl = work / f"tpl_{state}"
    pre = json.loads((work / f"tpl_{state}.json").read_text())
    n = len(pre)
    install_inline(split_layout_and_validation=control)
    # The writer's steps run INLINE on the reader's clock here, so a slow fsync
    # would be charged to the snapshot's 5 s busy deadline (a latency bound, not
    # a correctness one). Measured: 3 of 3,366 schedules hit it on a loaded host.
    LedgerStore.SNAPSHOT_TIMEOUT_S = 120.0
    counts: dict[str, int] = {}
    samples: list = []
    seq = [0]

    def one(positions):
        seq[0] += 1
        shutil.rmtree(work / f"i_{state}_{op}_{shard}_{seq[0] - 1}", ignore_errors=True)
        d = work / f"i_{state}_{op}_{shard}_{seq[0]}"
        shutil.copytree(tpl, d)
        p = d / "events.jsonl"
        w = LedgerStore(p)
        long_st = LedgerStore(p)
        with w._writer():
            w._ensure_fresh_locked()
            plan = w._plan_rotation_locked(key, "harness", "harness")
            steps = [
                lambda: w._journal_append_locked(plan["intent"]),
                lambda: (w._write_rotating_tmp_locked(plan["rot"]),
                         w._rename_with_retry(w.path, plan["closed"])),
                lambda: w._install_open_segment_locked(),
                lambda: (w._journal_append_locked({"op": "rotate-commit", "n": plan["n"],
                                                   "rotation_event_hash": plan["rot"].hash,
                                                   "closed_at": "2026-09-12T00:00:00+00:00"}),
                         w._recover_locked()),
            ]
            INLINE.__init__()
            if positions is not None:
                for pos, step in zip(positions, steps):
                    INLINE.at.setdefault(pos, []).append(step)
            INLINE.active = True
            try:
                kind, val = _reader_op(op, p, long_st, w)
            except Exception as exc:  # noqa: BLE001
                return "exception", f"{type(exc).__name__}: {exc}"[:200], INLINE.obs
            finally:
                INLINE.active = False
                for pos in sorted(INLINE.at):  # steps placed after the last observation
                    for step in INLINE.at[pos]:
                        step()
        c, why = _classify(kind, val, pre, n)
        return c, why, INLINE.obs

    # observations the read makes with an intent pending the whole time (the
    # most it makes: a pending intent adds stats of the closed name)
    _, _, m_obs = one((0, INF, INF, INF))
    schedules = list(itertools.combinations_with_replacement(range(m_obs + 1), 4))
    t0 = time.time()
    for idx, positions in enumerate(schedules):
        if idx % nshards != shard:
            continue
        c, why, _ = one(positions)
        counts[c] = counts.get(c, 0) + 1
        if c not in ("pass", "over") and len(samples) < 8:
            samples.append({"positions": positions, "class": c, "why": why})
    shutil.rmtree(work / f"i_{state}_{op}_{shard}_{seq[0]}", ignore_errors=True)
    emit({"state": state, "op": op, "shard": shard, "M": m_obs, "counts": counts,
          "samples": samples, "seconds": round(time.time() - t0, 1)})


# ----------------------------------------------------------- reader stress

REC = 78  # fixed-width ack record: "<12-digit length> <64-char hash>\n"


def read_ack(ackp: Path) -> tuple[int, str | None]:
    try:
        size = os.path.getsize(ackp)
    except FileNotFoundError:
        return 0, None
    k = size // REC
    if k == 0:
        return 0, None
    with open(ackp, "rb") as fh:
        fh.seek((k - 1) * REC)
        n, h = fh.read(REC).decode().split()
    return int(n), (None if h == "None" else h)


def check_read(st: LedgerStore, op: str, low: int, low_hash: str | None, t: Tally) -> None:
    try:
        if op == "verify":
            v = st.verify()
            t.add("reads_verify")
            if v.ok:
                if v.length < low:
                    t.add("SILENT_VERIFY", f"ok length {v.length} < acked {low}")
            elif "busy" in (v.reason or ""):
                t.add("busy", v.reason)
            else:
                t.add("false_break", f"low={low} {v.reason}")
        elif op == "events":
            evs = st.events()
            t.add("reads_events")
            if len(evs) < low:
                t.add("SILENT_EVENTS", f"events {len(evs)} < acked {low}")
            elif low_hash is not None and low > 0 and evs[low - 1].hash != low_hash:
                t.add("SILENT_EVENTS", f"event {low - 1} differs from acked")
        else:
            h = st.health_info()["event_count"]
            t.add("reads_health")
            if h < low:
                t.add("HEALTH_UNDER", f"health {h} < acked {low}")
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        t.add("busy" if "Busy" in name else "exception", f"{op} {name}: {exc}")


def stress_writer(d: Path, seconds: float, keyfile: str) -> None:
    key = _key(keyfile)
    p = d / "events.jsonl"
    ackp = d.parent / "acks.bin"
    st = LedgerStore(p)
    ackfd = os.open(str(ackp), os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
    acked: list[str] = []
    t = Tally()

    def ack(h):
        acked.append(h)
        os.write(ackfd, f"{len(acked):012d} {h:>64s}\n".encode())

    for i in range(300):
        ack(st.append("seed", {"i": i, "pad": "p" * 200}, agent_id=f"a{i % 3}").hash)
    stop = threading.Event()

    def thread_reader(ops):
        i = 0
        while not stop.is_set():
            low = len(acked)
            check_read(st, ops[i % len(ops)], low, acked[low - 1] if low else None, t)
            i += 1

    threads = [threading.Thread(target=thread_reader, args=(ops,), daemon=True)
               for ops in (["verify", "health"], ["events", "health"])]
    for th in threads:
        th.start()
    deadline = time.monotonic() + seconds
    appends = rotations = 0
    while time.monotonic() < deadline:
        try:
            for _ in range(random.randint(1, 3)):
                ack(st.append("w", {"pad": "p" * 200}, agent_id="w").hash)
                appends += 1
            ack(_rotate(st, key).rotation_event.hash)
            rotations += 1
        except Exception as exc:  # noqa: BLE001
            t.add("writer_exception", f"{type(exc).__name__}: {exc}")
            time.sleep(0.01)
    stop.set()
    for th in threads:
        th.join(60)
    fin = LedgerStore(p).verify()
    emit({"appends": appends, "rotations": rotations, "acked": len(acked),
          "final_ok": fin.ok, "final_length": fin.length, "tally": t.c, "samples": t.samples})


def stress_reader(d: Path, seconds: float, kind: str) -> None:
    p = d / "events.jsonl"
    ackp = d.parent / "acks.bin"
    t = Tally()
    deadline = time.monotonic() + seconds
    long_st = None
    ops = ["verify", "events", "health"]
    i = 0
    while time.monotonic() < deadline:
        low, low_hash = read_ack(ackp)
        try:
            if kind == "fresh" or long_st is None:
                st = LedgerStore(p)
                if kind == "long":
                    long_st = st
            else:
                st = long_st
        except Exception as exc:  # noqa: BLE001
            t.add("busy" if "Busy" in type(exc).__name__ else "open_exception",
                  f"{type(exc).__name__}: {exc}")
            continue
        check_read(st, ops[i % len(ops)], low, low_hash, t)
        i += 1
    emit({"kind": kind, "tally": t.c, "samples": t.samples})


# ------------------------------------------------------- two writer processes


def twowriters_service(d: Path, seconds: float, keyfile: str) -> None:
    key = _key(keyfile)
    st = LedgerStore(d / "events.jsonl")
    acked, errs = [], {}
    for i in range(50):
        acked.append(st.append("seed", {"i": i}, agent_id="s").hash)
    (d.parent / "seeded").write_text("1")
    end = time.monotonic() + seconds
    rotations = 0
    while time.monotonic() < end:
        try:
            acked.append(st.append("svc", {}, agent_id="s").hash)
            acked.append(st.append("svc", {}, agent_id="s").hash)
            acked.append(_rotate(st, key).rotation_event.hash)
            rotations += 1
        except Exception as exc:  # noqa: BLE001
            k = f"{type(exc).__name__}: {str(exc)[:120]}"
            errs[k] = errs.get(k, 0) + 1
            time.sleep(0.01)
    emit({"acked": acked, "errors": errs, "rotations": rotations})


def twowriters_cli(d: Path, seconds: float) -> None:
    while not (d.parent / "seeded").exists():
        time.sleep(0.01)
    acked, errs = [], {}
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:  # what `ledger append --path P` does: a fresh store per call
            acked.append(LedgerStore(d / "events.jsonl").append("cli", {}, agent_id="c").hash)
        except Exception as exc:  # noqa: BLE001
            k = f"{type(exc).__name__}: {str(exc)[:120]}"
            errs[k] = errs.get(k, 0) + 1
        time.sleep(0.02)
    emit({"acked": acked, "errors": errs})


# -------------------------------------------------------- torn append (G5)


def torn_appender(d: Path, seconds: float, keyfile: str) -> None:
    key = _key(keyfile)
    st = LedgerStore(d / "events.jsonl")
    rng = random.Random(7)
    end = time.monotonic() + seconds
    appends = rotations = 0
    (d.parent / "started").write_text("1")
    while time.monotonic() < end:
        st.append("w", {"pad": "x" * rng.randint(50, 3000)}, agent_id="w")
        appends += 1
        if appends % 40 == 0:
            _rotate(st, key)
            rotations += 1
    emit({"appends": appends, "rotations": rotations})


# ---------------------------------------------------------- many segments


def many_segments(d: Path, segments: int, fd_limit: int, keyfile: str) -> None:
    import resource  # POSIX only

    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (min(fd_limit, hard), hard))
    key = _key(keyfile)
    p = d / "events.jsonl"
    st = LedgerStore(p)
    st.append("seed", {})
    for _ in range(segments - 1):
        st.append("x", {})
        _rotate(st, key)
    out: dict = {"rlimit": resource.getrlimit(resource.RLIMIT_NOFILE)}
    try:
        v = LedgerStore(p).verify()
        out["verify"] = {"ok": v.ok, "length": v.length, "segments": v.segments, "reason": v.reason}
        out["events"] = len(LedgerStore(p).events())
        out["health"] = LedgerStore(p).health_info()["event_count"]
        from typer.testing import CliRunner

        from sealed_ledger.cli import app

        r = CliRunner().invoke(app, ["verify", "--path", str(p)])
        out["cli"] = [r.exit_code, r.stdout.splitlines()[:1]]
    except Exception as exc:  # noqa: BLE001
        out["exception"] = f"{type(exc).__name__}: {exc}"
    emit(out)


if __name__ == "__main__":
    mode, args = sys.argv[1], sys.argv[2:]
    if mode == "interleave":
        interleave_worker(Path(args[0]), args[1], args[2], int(args[3]), int(args[4]), args[5],
                          args[6] == "control")
    elif mode == "steps":
        steps_worker(Path(args[0]), args[1], args[2], int(args[3]), int(args[4]), args[5],
                     args[6] == "control")
    elif mode == "stress-writer":
        stress_writer(Path(args[0]), float(args[1]), args[2])
    elif mode == "stress-reader":
        stress_reader(Path(args[0]), float(args[1]), args[2])
    elif mode == "two-service":
        twowriters_service(Path(args[0]), float(args[1]), args[2])
    elif mode == "two-cli":
        twowriters_cli(Path(args[0]), float(args[1]))
    elif mode == "torn-appender":
        torn_appender(Path(args[0]), float(args[1]), args[2])
    elif mode == "many-segments":
        many_segments(Path(args[0]), int(args[1]), int(args[2]), args[3])
    else:
        raise SystemExit(f"unknown mode {mode}")
