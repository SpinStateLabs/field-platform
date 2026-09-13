"""C2 crash tests: a process killed at every step of a rotation never leaves
a silent GENESIS chain or a silently shortened one.

Two layers (C2 build spec §6.3):

1. Named steps. A subprocess rotates with ``FIELD_LEDGER_CRASH_AT=<step>`` and
   dies with ``os._exit(77)`` there, for the first and the second rotation.
   Then (a) a fresh store READS: verify is ok with every acked (global index,
   hash) present — or a reported break — never ok with fewer, and the read
   changes no file; (b) a fresh store RESTARTS with append, rotate, append:
   verify ok, the killed rotation rolled back or forward as its step implies,
   first hash unchanged (no new genesis).
2. A syscall-level sweep: every mutating filesystem call of
   ``append, append, rotate, append, append, rotate, append`` is counted in a
   subprocess and the process is killed before call K, for every K. With
   FIELD_SLOW_TESTS=1 each restart that does recovery work is itself killed at
   every call (double crash).

Process kills only: power loss is not tested (and Windows cannot fsync a
directory). The read and restart checks run in the test process on fresh
LedgerStore objects (a store keeps no state across instances); the killed
writers are real subprocesses.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ledger_c2_support import KEY_PRIV, SLOW, fill, journal_records, listing, rotate
from sealed_ledger.cli import app as cli_app
from sealed_ledger.store import LedgerStore, journal_path_for

runner = CliRunner()
JOBS = max(2, min(8, os.cpu_count() or 2))

ROLLED_BACK = [  # the rename never happened: the open file still holds everything
    "rotate.before_intent",
    "rotate.intent_torn",
    "rotate.after_intent",
    "rotate.segment_tmp_torn",
    "rotate.segment_tmp_written",
]
ROLLED_FORWARD = [  # the rename happened: recovery finishes the rotation
    "rotate.after_rename",  # plan C-gate item: between the rename and the metadata write
    "rotate.after_segment_created",
    "rotate.commit_torn",
    "rotate.after_commit",
]

_ROTATE_CHILD = textwrap.dedent("""
    import sys
    from sealed_ledger.store import LedgerStore
    key = open(sys.argv[2], encoding="ascii").read()
    LedgerStore(sys.argv[1]).rotate(private_key_pem=key, operator="crash", reason="crash test")
    print("NO CRASH")
""")


def _env(**extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "FIELD_LEDGER_CRASH_AT"}
    env.update(PYTHONIOENCODING="utf-8", **extra)
    return env


def _read_check(p: Path, acked: list[str]) -> str:
    """'full' (ok, every acked event in place) or 'break'; raises on a silent short chain
    or on a read that changed a file."""
    before = listing(p.parent)
    store = LedgerStore(p)
    v = store.verify()
    hashes = [e.hash for e in store.events()]
    health = store.health_info()["event_count"]
    cli = runner.invoke(cli_app, ["verify", "--path", str(p)])
    assert listing(p.parent) == before, "a read changed the ledger directory"
    if not v.ok:
        assert cli.exit_code == 1, cli.output
        return "break"
    assert v.length >= len(acked), f"SILENT: ok length {v.length} < acked {len(acked)}"
    assert hashes[: len(acked)] == acked, "SILENT: an acked event is missing or moved"
    assert health >= len(acked) and cli.exit_code == 0, (health, cli.output)
    return "full"


def _restart_check(p: Path, acked: list[str], extra_ok: range) -> tuple[int, list[str]]:
    store = LedgerStore(p)
    store.append("restart", {}, agent_id="r")
    rotate(store, "restart")
    store.append("restart", {}, agent_id="r")
    v = LedgerStore(p).verify()
    assert v.ok, v.reason
    hashes = [e.hash for e in LedgerStore(p).events()]
    assert v.length - len(acked) - 3 in extra_ok, (v.length, len(acked))
    assert hashes[: len(acked)] == acked, "an acked event was lost on restart"
    assert hashes[0] == acked[0], "chain restarted from a different genesis"
    return v.length, hashes


# ---------------------------------------------------------------- named steps

_CASES = [(step, which) for step in ROLLED_BACK + ROLLED_FORWARD for which in ("first", "second")]


@pytest.fixture(scope="module")
def crashed_states(tmp_path_factory):
    """Build every case, then kill all the rotating children concurrently."""
    root = tmp_path_factory.mktemp("c2-crash")
    key = root / "anchor.pem"
    key.write_text(KEY_PRIV, encoding="ascii")
    cases = {}
    for step, which in _CASES:
        p = root / f"{which}-{step.replace('.', '_')}" / "events.jsonl"
        s = LedgerStore(p)
        acked = [e.hash for e in fill(s, 4)]
        if which == "second":
            acked.append(rotate(s).rotation_event.hash)
            acked += [e.hash for e in fill(s, 3)]
        cases[(step, which)] = (p, acked)

    def kill(case):
        (step, which), (p, _) = case
        return (step, which), subprocess.run(
            [sys.executable, "-c", _ROTATE_CHILD, str(p), str(key)], capture_output=True,
            text=True, encoding="utf-8", errors="replace", timeout=300,
            env=_env(FIELD_LEDGER_CRASH_AT=step),
        )

    with ThreadPoolExecutor(JOBS) as pool:
        results = dict(pool.map(kill, cases.items()))
    return cases, results


@pytest.mark.parametrize("step,which", _CASES)
def test_crash_at_each_rotation_step_never_silent_and_recovers(crashed_states, step, which):
    cases, results = crashed_states
    p, acked = cases[(step, which)]
    child = results[(step, which)]
    assert child.returncode == 77, (child.returncode, child.stdout, child.stderr[-800:])

    assert _read_check(p, acked) == "full"  # no step of a rotation leaves a break either

    forward = step in ROLLED_FORWARD
    length, hashes = _restart_check(p, acked, range(1, 2) if forward else range(0, 1))
    ops = [r["op"] for r in journal_records(p)]
    prior = ["rotate-intent", "rotate-commit"] if which == "second" else []
    if forward:
        assert ops[: len(prior) + 2] == prior + ["rotate-intent", "rotate-commit"]
        killed = journal_records(p)[len(prior)]
        assert hashes[len(acked)] == killed["rotation_event"]["hash"]  # the killed rotation's event
        if step != "rotate.after_commit":
            assert journal_records(p)[len(prior) + 1].get("recovered") is True
    elif step in ("rotate.before_intent", "rotate.intent_torn"):
        assert ops[: len(prior)] == prior and ops[len(prior)] == "rotate-intent"  # only the restart's
        assert journal_records(p)[len(prior)]["start_index"] == (0 if which == "first" else 4)
    else:
        assert ops[len(prior): len(prior) + 2] == ["rotate-intent", "rotate-abort"]
        assert journal_records(p)[len(prior) + 1]["reason"] == "recovered: crash before rename"
    assert not (p.parent / ".events.jsonl.rotating").exists()
    assert LedgerStore(p).verify().segments == (3 if forward else 2) + (1 if which == "second" else 0)


# ------------------------------------------------------------- syscall sweep

_SWEEP_CHILD = textwrap.dedent(r"""
    import builtins, io, os, sys
    from pathlib import Path
    from sealed_ledger.store import LedgerStore
    import field_core.signing  # import cost outside the hooked region

    mode, d, K, keyfile = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    key = open(keyfile, encoding="ascii").read()
    _write, _open, _exit = os.write, os.open, os._exit
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0)
    ackfd = _open(str(d) + ".acks", flags, 0o644)
    markfd = _open(str(d) + (".mark" if mode == "child" else ".mark2"), flags, 0o644)
    skip = {ackfd, markfd}
    counter = [0]

    def trip(name):
        counter[0] += 1
        if counter[0] == K:
            _write(markfd, f"{K}\t{name}\n".encode())
            _exit(9)

    def wrap(obj, attr, filt=None):
        orig = getattr(obj, attr)
        def hooked(*a, **k):
            if filt is None or filt(*a, **k):
                trip(attr)
            return orig(*a, **k)
        setattr(obj, attr, hooked)

    def fd_of(x):
        return x.fileno() if hasattr(x, "fileno") else x

    p = d / "events.jsonl"
    store = LedgerStore(p)
    acked = 0
    def ack(h):
        global acked
        _write(ackfd, f"{acked}\t{h}\n".encode())
        acked += 1
    if mode == "child":
        for i in range(3):
            ack(store.append("seed", {"i": i}, agent_id="a").hash)
    WRITE = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC
    wrap(os, "write", lambda fd, *a, **k: fd not in skip)
    wrap(os, "fsync", lambda fd, *a, **k: fd_of(fd) not in skip)
    for name in ("rename", "replace", "ftruncate", "truncate", "unlink", "remove"):
        wrap(os, name)
    wrap(os, "open", lambda path, fl, *a, **k: bool(fl & WRITE))
    real_open = builtins.open
    def open_hooked(*a, **k):
        m = a[1] if len(a) > 1 else k.get("mode", "r")
        if not isinstance(a[0], int) and isinstance(m, str) and any(c in m for c in "wax+"):
            trip("open")
        return real_open(*a, **k)
    builtins.open = io.open = open_hooked
    if mode == "child":
        for j, op in enumerate("aaraara"):
            if op == "a":
                ack(store.append("w", {"j": j}, agent_id="a").hash)
            else:
                ack(store.rotate(private_key_pem=key, operator="sweep", reason="sweep").rotation_event.hash)
    else:  # restart, killed at call K (K = -1: count only)
        store.append("restart", {}, agent_id="r")
        store.rotate(private_key_pem=key, operator="sweep", reason="restart")
        store.append("restart", {}, agent_id="r")
    _write(markfd, f"DONE\t{counter[0]}\n".encode())
    _exit(0)
""")


def _sweep_run(mode: str, d: Path, k: int, keyfile: Path) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", _SWEEP_CHILD, mode, str(d), str(k), str(keyfile)],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=300, env=_env())


def _acks(d: Path) -> list[str]:
    f = Path(str(d) + ".acks")
    return [line.split("\t")[1] for line in f.read_text().splitlines()] if f.exists() else []


def _mark(d: Path, suffix: str = ".mark") -> str:
    f = Path(str(d) + suffix)
    return f.read_text() if f.exists() else ""


def test_syscall_level_crash_sweep_every_read_full_every_restart_recovered(tmp_path):
    keyfile = tmp_path / "anchor.pem"
    keyfile.write_text(KEY_PRIV, encoding="ascii")
    rows: dict[int, dict] = {}
    total = None
    k = 1
    while total is None or k <= total + 1:
        batch = list(range(k, k + JOBS))
        k += JOBS

        def one(kk):
            d = tmp_path / f"k{kk:03d}" / "ledger"
            d.mkdir(parents=True)
            r = _sweep_run("child", d, kk, keyfile)
            return kk, d, r

        with ThreadPoolExecutor(JOBS) as pool:
            for kk, d, r in pool.map(one, batch):
                mark = _mark(d)
                assert r.returncode in (0, 9), (kk, r.stderr[-800:])
                rows[kk] = {"d": d, "mark": mark.strip()}
                if mark.startswith("DONE") and total is None:
                    total = int(mark.split("\t")[1])
        assert k < 500, "sweep did not terminate"
    killed = {kk: row for kk, row in rows.items() if not row["mark"].startswith("DONE")}
    assert len(killed) == total, (len(killed), total)
    classes: dict[str, int] = {}
    double_targets = []
    for kk, row in sorted(killed.items()):
        p = row["d"] / "events.jsonl"
        acked = _acks(row["d"])
        cls = _read_check(p, acked)
        classes[cls] = classes.get(cls, 0) + 1
        snap = tmp_path / f"k{kk:03d}" / "snap"
        if SLOW:
            import shutil

            shutil.copytree(row["d"], snap)
            counting = tmp_path / f"k{kk:03d}" / "count"
            shutil.copytree(row["d"], counting)
            _sweep_run("restart", counting, -1, keyfile)
            calls = int(_mark(counting, ".mark2").split("\t")[1])
            double_targets.append((kk, snap, acked, calls))
        _restart_check(p, acked, range(0, 2))
    assert classes.get("full", 0) + classes.get("break", 0) == total
    assert classes.get("break", 0) == 0, classes  # every crash point leaves the full chain
    print(f"\nsyscall sweep: {total} crash points, reads {classes}")
    if not SLOW:
        return
    baseline = min(c for _, _, _, c in double_targets)
    runs = 0
    for kk, snap, acked, calls in double_targets:
        if calls == baseline:
            continue  # this restart did no recovery work
        for k2 in range(1, calls + 1):
            import shutil

            d2 = tmp_path / f"k{kk:03d}_r{k2:03d}" / "ledger"
            shutil.copytree(snap, d2)
            _sweep_run("restart", d2, k2, keyfile)
            assert _read_check(d2 / "events.jsonl", acked) == "full"  # the spec lab: every double-crash read full
            _restart_check(d2 / "events.jsonl", acked, range(0, 5))
            runs += 1
    print(f"double-crash runs: {runs}")
