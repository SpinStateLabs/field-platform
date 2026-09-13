"""C2 readers: no reader (thread, fresh store, other process, CLI) ever sees an
empty or short chain that verifies ok while a ledger rotates, and a second
writer process never loses an acknowledged event.

Every heavy test runs a bounded version by default (the whole sealed-ledger
suite stays under 3 minutes on a laptop) and the build spec's full durations
with FIELD_SLOW_TESTS=1. The subprocess side lives in ``ledger_c2_harness.py``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from ledger_c2_support import KEY_PRIV, SLOW, archive_oldest_for_test, fill, rotate
from sealed_ledger.store import LedgerStore

HARNESS = Path(__file__).resolve().parent / "ledger_c2_harness.py"
JOBS = max(2, min(8, os.cpu_count() or 2))


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("FIELD_LEDGER_CRASH_AT",)}
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _spawn(*args: str) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(HARNESS), *args], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, encoding="utf-8",
                            errors="replace", env=_env())


def _result(proc: subprocess.Popen, timeout: float = 900) -> dict:
    out, err = proc.communicate(timeout=timeout)
    for line in out.splitlines():
        if line.startswith("JSON"):
            return json.loads(line[4:])
    raise AssertionError(f"harness produced no result (rc {proc.returncode}): {err[-1500:]}")


def _keyfile(tmp_path: Path) -> Path:
    f = tmp_path / "anchor.pem"
    f.write_text(KEY_PRIV, encoding="ascii")
    return f


# ------------------------------------------------------------ interleavings

OPS = ["verify_fresh", "events_long", "health_fresh", "health_writer", "verify_writer"]


def _interleave(tmp_path: Path, states, ops, control: bool, mode: str = "interleave",
                stride: int = 1) -> dict:
    """Run a checker over (state, op), sharded across JOBS processes. ``stride``
    > 1 runs a deterministic 1/stride sample of the schedules."""
    sys.path.insert(0, str(HARNESS.parent))
    import ledger_c2_harness as harness

    work = tmp_path / f"{mode}-{'control' if control else 'design'}"
    work.mkdir()
    keyfile = _keyfile(tmp_path)
    for state in states:
        pre = harness.build_template(work / f"tpl_{state}", KEY_PRIV, state)
        (work / f"tpl_{state}.json").write_text(json.dumps(pre))
    tasks = [(st, op, shard) for st in states for op in ops for shard in range(JOBS)]
    results, running = [], []
    while tasks or running:
        while tasks and len(running) < JOBS:
            st, op, shard = tasks.pop(0)
            running.append(_spawn(mode, str(work), st, op, str(shard), str(JOBS * stride),
                                  str(keyfile), "control" if control else "design"))
        time.sleep(0.1)
        for proc in list(running):
            if proc.poll() is not None:
                results.append(_result(proc))
                running.remove(proc)
    total: dict[str, int] = {}
    samples = []
    for r in results:
        for k, v in r["counts"].items():
            total[k] = total.get(k, 0) + v
        samples += r["samples"][:2]
    return {"total": total, "samples": samples}


def _no_bad_schedule(out: dict, minimum: int) -> None:
    total = out["total"]
    bad = {k: v for k, v in total.items() if k not in ("pass", "over")}
    assert bad == {}, (bad, out["samples"][:6])
    assert total.get("pass", 0) >= minimum, total


def test_interleavings_rotate_vs_readers(tmp_path):
    """A real rotate() in a writer thread parked before each mutating call vs
    five real read operations, first and second rotation (build spec §6.4; the
    spec lab: W 5,293 / L 6,564 pass). Default: a deterministic 1/24 sample;
    FIELD_SLOW_TESTS=1: every schedule."""
    stride = 1 if SLOW else 24
    out = _interleave(tmp_path, ["first", "second"], OPS, control=False, stride=stride)
    print(f"\ninterleavings (1/{stride} of schedules): {out['total']}")
    _no_bad_schedule(out, 5000 // stride)


STEP_OPS_DEFAULT = ["events_long", "health_writer", "verify_writer"]  # one snapshot each: cheap


def test_step_placement_rotate_vs_readers(tmp_path):
    """Each rotation step (intent; tmp + rename; new open segment; commit)
    placed independently before any reader observation — several parks per
    schedule, which the single-park checker above cannot express. Default: a
    deterministic 1/8 sample of the three single-snapshot reads;
    FIELD_SLOW_TESTS=1: every schedule of all five."""
    ops = OPS if SLOW else STEP_OPS_DEFAULT
    stride = 1 if SLOW else 8
    out = _interleave(tmp_path, ["first", "second"], ops, control=False, mode="steps", stride=stride)
    print(f"\nstep placement ({', '.join(ops)}; 1/{stride} of schedules): {out['total']}")
    _no_bad_schedule(out, 3000 // stride)


def test_step_placement_checker_catches_a_layout_validation_split(tmp_path):
    """Negative control (build spec §6.4, trap 1): deciding the layout from its
    own stats instead of the observations the snapshot re-validates must be
    caught, or the checkers prove nothing. (The single-park checker cannot
    catch this defect: running the writer to completion always includes the
    commit, which forces a retry — measured 0 of 4,854 schedules on Windows.)"""
    ops = ["events_long", "verify_fresh"] if SLOW else ["events_long"]
    stride = 1 if SLOW else 3
    out = _interleave(tmp_path, ["first", "second"], ops, control=True, mode="steps", stride=stride)
    print(f"\ncontrol (split layout/validation; 1/{stride} of schedules): {out['total']}")
    caught = sum(v for k, v in out["total"].items() if k in ("VIOLATION", "false_break", "exception"))
    assert caught > 0, out["total"]
    assert out["total"].get("VIOLATION", 0) > 0, out["total"]  # a silent short chain, not only breaks


# ------------------------------------------------------------ reader stress


def test_reader_stress_threads_processes_and_cli_see_no_short_chain(tmp_path):
    seconds = 30.0 if SLOW else 5.0
    d = tmp_path / "ledger"
    d.mkdir()
    keyfile = _keyfile(tmp_path)
    writer = _spawn("stress-writer", str(d), str(seconds), str(keyfile))
    ackp = tmp_path / "acks.bin"
    deadline = time.monotonic() + 120
    sys.path.insert(0, str(HARNESS.parent))
    import ledger_c2_harness as harness

    while harness.read_ack(ackp)[0] < 300 and time.monotonic() < deadline:
        time.sleep(0.05)
    readers = [_spawn("stress-reader", str(d), str(seconds), kind) for kind in ("fresh", "fresh", "long")]
    cli = {"runs": 0, "silent": [], "false_break": [], "other": []}
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        low, _ = harness.read_ack(ackp)
        r = subprocess.run([sys.executable, "-m", "sealed_ledger.cli", "verify", "--path",
                            str(d / "events.jsonl")], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=_env(), timeout=300)
        cli["runs"] += 1
        out = r.stdout + r.stderr
        m = re.search(r"OK — chain intact over (\d+) events", out)
        if m:
            if int(m.group(1)) < low:
                cli["silent"].append(out[:200])
        elif "BUSY" not in out:
            (cli["false_break"] if "TAMPERED" in out else cli["other"]).append(out[-300:])
    w = _result(writer)
    rs = [_result(p) for p in readers]
    tallies = [w["tally"]] + [r["tally"] for r in rs]
    agg: dict[str, int] = {}
    for t in tallies:
        for k, v in t.items():
            agg[k] = agg.get(k, 0) + v
    print(f"\nstress {seconds:.0f}s: rotations {w['rotations']}, reads {agg}, cli runs {cli['runs']}")
    violations = {k: v for k, v in agg.items()
                  if k.startswith("SILENT") or k in ("HEALTH_UNDER", "false_break", "exception",
                                                     "open_exception", "writer_exception")}
    assert violations == {}, (violations, w["samples"], [r["samples"] for r in rs])
    assert cli["silent"] == [] and cli["false_break"] == [] and cli["other"] == [], cli
    assert w["final_ok"] and w["final_length"] == w["acked"]
    assert w["rotations"] > 0 and agg.get("reads_verify", 0) > 0


def test_second_writer_process_loses_no_acknowledged_event(tmp_path):
    """Plan P4 / judge D4: a `ledger append --path`-style process appends while
    the service process appends and rotates. Every ack from both is in the chain."""
    seconds = 20.0 if SLOW else 10.0
    d = tmp_path / "ledger"
    d.mkdir()
    keyfile = _keyfile(tmp_path)
    service = _spawn("two-service", str(d), str(seconds), str(keyfile))
    cli = _spawn("two-cli", str(d), str(seconds))
    s, c = _result(service), _result(cli)
    have = [e.hash for e in LedgerStore(d / "events.jsonl").events()]
    v = LedgerStore(d / "events.jsonl").verify()
    print(f"\ntwo writers {seconds:.0f}s: service {len(s['acked'])} acks / {s['rotations']} rotations, "
          f"cli {len(c['acked'])} acks, errors {s['errors']} {c['errors']}")
    assert v.ok and v.length == len(have)
    have_set = set(have)
    assert [h for h in s["acked"] if h not in have_set] == []
    assert [h for h in c["acked"] if h not in have_set] == []
    assert len(have) == len(s["acked"]) + len(c["acked"])
    assert s["errors"] == {} and s["rotations"] > 0 and len(c["acked"]) > 0
    # the only acceptable CLI failure is a loud busy (never observed with one CLI writer)
    assert all(k.startswith("LedgerBusy") for k in c["errors"]), c["errors"]


def test_reader_never_fails_on_append_in_flight(tmp_path):
    """G5: an append half copied into the page cache is re-read, not believed."""
    seconds = 20.0 if SLOW else 3.0
    d = tmp_path / "ledger"
    d.mkdir()
    keyfile = _keyfile(tmp_path)
    appender = _spawn("torn-appender", str(d), str(seconds), str(keyfile))
    deadline = time.monotonic() + 120
    while not (tmp_path / "started").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    stop = time.monotonic() + seconds
    bad: list = []
    reads = [0]

    def reader():
        while time.monotonic() < stop:
            try:
                v = LedgerStore(d / "events.jsonl").verify()
                if not v.ok and "busy" not in (v.reason or ""):
                    bad.append(v.reason)
            except Exception as exc:  # noqa: BLE001
                bad.append(repr(exc))
            reads[0] += 1

    threads = [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(300)
    a = _result(appender)
    print(f"\nappend in flight: {reads[0]} reads during {a['appends']} appends / {a['rotations']} rotations")
    assert bad == [], bad[:3]
    assert reads[0] > 0 and a["appends"] > 0


def test_readers_during_rotate_and_archive_never_see_a_short_ok_chain(tmp_path):
    seconds = 8.0 if SLOW else 3.0
    d = tmp_path / "data" / "ledger"
    s = LedgerStore(d / "events.jsonl")
    fill(s, 20)
    stop = time.monotonic() + seconds
    acked = [20]
    bad: list = []
    reads = [0]
    errors: list = []

    def writer():
        k = 0
        try:
            while time.monotonic() < stop:
                for _ in range(3):
                    s.append("w", {"k": k})
                    acked[0] += 1
                rotate(s)
                acked[0] += 1
                k += 1
                if k % 3 == 0:
                    archive_oldest_for_test(s, tmp_path / "data" / "archive")
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))

    def reader(fresh: bool):
        while time.monotonic() < stop:
            low = acked[0]
            v = (LedgerStore(d / "events.jsonl") if fresh else s).verify()
            reads[0] += 1
            if not v.ok:
                bad.append(("not ok", v.reason))
            elif v.length < low:
                bad.append(("SHORT", v.length, low))

    threads = [threading.Thread(target=writer)] + [
        threading.Thread(target=reader, args=(f,)) for f in (True, False, True)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)
    assert errors == [] and bad == [], (errors, bad[:5])
    final = LedgerStore(d / "events.jsonl").verify()
    print(f"\nreaders during archive: {reads[0]} reads; archived {final.archived_segments}")
    assert final.ok and final.length == acked[0] and final.archived_segments > 0


@pytest.mark.skipif(os.name == "nt", reason="RLIMIT_NOFILE is POSIX")
def test_many_live_segments_under_low_fd_limit(tmp_path):
    d = tmp_path / "ledger"
    d.mkdir()
    out = _result(_spawn("many-segments", str(d), "600", "256", str(_keyfile(tmp_path))))
    assert "exception" not in out, out
    assert out["rlimit"][0] == 256
    assert out["verify"]["ok"] and out["verify"]["segments"] == 600
    assert out["events"] == out["verify"]["length"] == out["health"]
    assert out["cli"][0] == 0, out
