"""GL go-live regression: /health answers inside its 5 s budget while ONE whole-ledger request runs, on a
CPU-limited ledger process (T6: tools/health_under_load.py, docs/capstone-evidence/t6-health-under-load.md).

Offline and loopback only: a real ``ledger serve`` subprocess on 127.0.0.1 and a fixture ledger file written
here. Nothing leaves the host, no secret is used. The server is killed after every test.

CPU limiting (two methods; each test skips with an explicit reason where its method is unavailable, and the
skip is never a pass):

* ``cfs-quota`` (the faithful one): the server joins a cgroup whose Linux CFS bandwidth quota is 1/16 CPU
  (6.25 ms per 100 ms), the Fly shared-vCPU baseline T6 used. Needs a writable cgroup v1 ``cpu`` hierarchy or
  a delegated cgroup v2 (typically root in a container or VM). It is verified, not assumed: the test fails
  if the cgroup's ``nr_throttled`` stays 0, i.e. if the quota never bit.
* ``one-core-pin`` (the fallback, weaker): the server is pinned to ONE CPU with ``os.sched_setaffinity`` (what
  ``taskset -c`` does). No quota, so the load is only as heavy as the ledger size makes it, hence the larger
  ledger. Needs Linux and at least two CPUs in this process's affinity set.

Each test also fails (rather than passes vacuously) if the heavy request was too short to overlap enough
/health polls. A poll fails when it is not HTTP 200 or takes 5 s or more (the estate monitor's rule).
"""

from __future__ import annotations

import http.client
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from field_core.ledger import make_event

HEALTH_BUDGET_S = 5.0
POLL_EVERY_S = 0.1  # ten times the estate monitor's rate: a tighter net, not a looser one
MIN_OVERLAP_POLLS = 5  # polls that started while the heavy request was in flight
MIN_HEAVY_S = 0.5  # a heavy request shorter than this did not load the process
QUOTA_CPUS = 1 / 16
CFS_PERIOD_US = 100_000
# events; ~600 bytes per stored row. Sized so that EACH whole-ledger read, if it ran inline on the event loop,
# would block /health for longer than HEALTH_BUDGET_S, so the 5 s budget alone catches that regression (the
# overlap guard below is a second net, not the only one). cfs-quota /events: 30k took ~2.3 s inline at 1/16 CPU,
# inside the budget; 60k blocks ~16 s (measured; 55k only ~5.4 s, too thin). /verify is slower per event, 30k
# already blocks ~5.2 s. one-core-pin: 100k, as before.
SIZES = {("cfs-quota", "/events"): 60_000, ("cfs-quota", "/verify"): 30_000,
         ("one-core-pin", "/events"): 100_000, ("one-core-pin", "/verify"): 100_000}
ROUTES = ("/events", "/verify")  # the two whole-ledger reads (unfiltered /events, full-chain /verify)


def _cfs_cgroup_parent() -> tuple[str, Path] | tuple[None, str]:
    """('v1'|'v2', parent dir) of a cgroup in which we can create a child, else (None, reason)."""
    mnt = Path("/sys/fs/cgroup")
    try:
        lines = Path("/proc/self/cgroup").read_text().splitlines()
    except OSError as exc:
        return None, f"/proc/self/cgroup unreadable ({exc})"
    for ln in lines:
        _, ctrls, rel = ln.split(":", 2)
        if "cpu" in ctrls.split(","):  # cgroup v1 cpu controller
            parent = mnt / "cpu" / rel.lstrip("/")
            if (parent / "cpu.cfs_quota_us").exists():
                return "v1", parent
    if (mnt / "cgroup.controllers").exists():  # cgroup v2
        rel = next((ln.split(":", 2)[2] for ln in lines if ln.startswith("0::")), "/")
        return "v2", mnt / rel.lstrip("/")
    return None, "no cgroup v1 cpu hierarchy and no cgroup v2 mount"


class CfsQuota:
    """A throwaway cgroup with a CFS quota. ``probe()`` is a real probe: it creates one, sets the quota, moves a
    throwaway child process into it and removes it."""

    def __init__(self, parent_kind: str, parent: Path) -> None:
        self.kind, self.dir = parent_kind, parent / f"ledger-t6-{os.getpid()}-{time.monotonic_ns()}"

    @classmethod
    def probe(cls) -> tuple["CfsQuota | None", str]:
        kind, parent = _cfs_cgroup_parent()
        if kind is None:
            return None, str(parent)
        step = "create a cgroup with a CFS quota"
        try:
            q = cls(kind, parent)
            q.dir.mkdir()
            try:
                q._set_quota()
                step = "move a process into a cgroup with a CFS quota"  # a host can allow the first and refuse this
                q._try_attach()
            finally:
                q.dir.rmdir()
        except OSError as exc:
            return None, f"cannot {step} under {parent} ({type(exc).__name__}: {exc})"
        return cls(kind, parent), ""

    def _set_quota(self) -> None:
        quota = int(QUOTA_CPUS * CFS_PERIOD_US)
        if self.kind == "v1":
            (self.dir / "cpu.cfs_period_us").write_text(str(CFS_PERIOD_US))
            (self.dir / "cpu.cfs_quota_us").write_text(str(quota))
        else:
            (self.dir / "cpu.max").write_text(f"{quota} {CFS_PERIOD_US}")

    def _move(self, pid: int) -> None:
        (self.dir / "cgroup.procs").write_text(str(pid))  # whole thread group, every thread

    def _try_attach(self) -> None:
        """Move a throwaway child into the group, as ``attach`` will move the server; the child is always ended."""
        child = subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE)
        try:
            self._move(child.pid)
        finally:
            child.kill()
            child.wait(30)  # reaped: the group is empty again and can be removed
            child.stdin.close()

    def attach(self, pid: int) -> None:
        self.dir.mkdir()
        self._set_quota()
        self._move(pid)

    def nr_throttled(self) -> int:
        for ln in (self.dir / "cpu.stat").read_text().splitlines():
            if ln.startswith("nr_throttled"):
                return int(ln.split()[1])
        return 0

    def remove(self) -> None:
        try:
            self.dir.rmdir()
        except OSError:
            pass


def _pin_cpu() -> tuple[int | None, str]:
    if not hasattr(os, "sched_setaffinity"):
        return None, "os.sched_setaffinity is not available on this platform"
    cpus = sorted(os.sched_getaffinity(0))
    if len(cpus) < 2:
        return None, f"only {len(cpus)} CPU in this process's affinity set: pinning to one core limits nothing"
    return cpus[-1], ""


@pytest.fixture(scope="module")
def ledgers(tmp_path_factory):
    """data dir per size, built lazily and shared by the module's tests (the server only reads it)."""
    made: dict[int, Path] = {}

    def get(n: int) -> Path:
        if n not in made:
            root = tmp_path_factory.mktemp(f"gl-t6-{n}")
            (root / "ledger").mkdir()
            prev = "0" * 64
            with open(root / "ledger" / "events.jsonl", "w", encoding="utf-8") as fh:
                for i in range(n):
                    e = make_event("action", {"i": i, "tool": "t", "pad": "x" * 260}, prev_hash=prev,
                                   agent_id=f"agent-{i % 40:03d}")
                    fh.write(e.model_dump_json() + "\n")
                    prev = e.hash
            made[n] = root
        return made[n]

    return get


def _get(port: int, path: str, timeout: float) -> tuple[int | str, float, int]:
    t0 = time.monotonic()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)  # direct: no proxy involved
        conn.request("GET", path)
        resp = conn.getresponse()
        size = len(resp.read())
        conn.close()
        return resp.status, time.monotonic() - t0, size
    except Exception as exc:  # noqa: BLE001 - a timeout or a reset is a failed poll, by name
        return type(exc).__name__, time.monotonic() - t0, 0


def _failed(status: int | str, seconds: float) -> bool:
    return status != 200 or seconds >= HEALTH_BUDGET_S


def _port_the_server_took(log_path, proc, deadline: float) -> int:
    """The port ``ledger serve --port 0`` bound, read from the line uvicorn logs once it listens."""
    while time.monotonic() < deadline:
        text = log_path.read_text(encoding="utf-8", errors="replace")
        found = re.search(r"Uvicorn running on http://127\.0\.0\.1:(\d+) ", text)
        if found and int(found.group(1)):
            return int(found.group(1))
        assert proc.poll() is None, text[-2000:]
        time.sleep(0.2)
    raise AssertionError("the server did not say which port it took: " + text[-2000:])


def _run_under_load(data_dir: Path, tmp_path: Path, route: str, *, pin: int | None = None,
                    quota: CfsQuota | None = None) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("FIELD_")}
    env["FIELD_DATA_DIR"] = str(data_dir)
    preexec = (lambda: os.sched_setaffinity(0, {pin})) if pin is not None else None
    log = open(tmp_path / "server.log", "w", encoding="utf-8")
    srv = subprocess.Popen([sys.executable, "-m", "sealed_ledger.cli", "serve", "--host", "127.0.0.1",
                            "--port", "0"], env=env, stdout=log, stderr=subprocess.STDOUT,
                           preexec_fn=preexec)
    stop = threading.Event()
    polls: list[tuple[float, int | str, float]] = []
    poller = threading.Thread(target=lambda: _poll(port, stop, polls), daemon=True)
    try:
        deadline = time.monotonic() + 120
        port = _port_the_server_took(tmp_path / "server.log", srv, deadline)
        while _get(port, "/health", 2.0)[0] != 200:
            assert srv.poll() is None and time.monotonic() < deadline, (tmp_path / "server.log").read_text()[-2000:]
            time.sleep(0.3)
        if quota is not None:
            quota.attach(srv.pid)  # after start-up: the limit applies to serving, not to the first load
        poller.start()
        time.sleep(1.0)
        start = time.monotonic()
        status, seconds, size = _get(port, route, 300)
        end = time.monotonic()
        time.sleep(1.0)
        stop.set()
        poller.join(HEALTH_BUDGET_S + 5)
        throttled = quota.nr_throttled() if quota is not None else None
    finally:
        stop.set()
        srv.kill()
        srv.wait(30)
        log.close()
        if quota is not None:
            quota.remove()
    before = [p for p in polls if p[0] < start]
    during = [p for p in polls if start <= p[0] <= end]
    return {"status": status, "seconds": seconds, "bytes": size, "throttled": throttled, "before": before,
            "during": during, "max_health": max((p[2] for p in during), default=0.0),
            "failed": [p for p in during if _failed(p[1], p[2])]}


def _poll(port: int, stop: threading.Event, polls: list) -> None:
    while not stop.is_set():
        t = time.monotonic()
        status, seconds, _ = _get(port, "/health", HEALTH_BUDGET_S)
        polls.append((t, status, seconds))
        stop.wait(max(0.0, POLL_EVERY_S - (time.monotonic() - t)))


def _check(res: dict, route: str, method: str) -> None:
    print(f"\nGL-T6 {method} {route}: heavy {res['status']} in {res['seconds']:.2f} s ({res['bytes']} B); "
          f"/health polls during {len(res['during'])}, failed {len(res['failed'])}, "
          f"max {res['max_health']:.3f} s, cfs nr_throttled {res['throttled']}")
    assert res["status"] == 200, f"the heavy request itself failed: {res['status']}"
    # non-vacuity: the load must have been real
    assert res["seconds"] >= MIN_HEAVY_S, (
        f"heavy request took {res['seconds']:.2f} s < {MIN_HEAVY_S} s: the CPU limit did not load the process")
    # the claim comes BEFORE the overlap guard, so a stalled event loop reads as a missed budget, not as a setup problem
    assert not res["failed"], f"/health missed its {HEALTH_BUDGET_S} s budget during {route}: {res['failed'][:5]}"
    assert res["max_health"] < HEALTH_BUDGET_S
    assert len(res["during"]) >= MIN_OVERLAP_POLLS, (
        f"/health stalled or the load was too short: only {len(res['during'])} polls started during the heavy "
        f"request (need {MIN_OVERLAP_POLLS}); max /health {res['max_health']:.2f} s. A blocked event loop stops "
        f"new polls from starting")
    assert len(res["before"]) >= 3 and not any(_failed(p[1], p[2]) for p in res["before"]), "idle /health failed"


def _probe_on_a_stand_in(monkeypatch, parent: Path, *, set_error: OSError | None = None,
                         move_error: OSError | None = None):
    """Runs the real ``probe()`` against a plain directory: only the two cgroup file writes are stood in."""
    moved: list[int] = []
    children: list[subprocess.Popen] = []
    real_popen = subprocess.Popen

    def popen(*args, **kwargs):
        children.append(real_popen(*args, **kwargs))
        return children[-1]

    def set_quota(self) -> None:
        if set_error is not None:
            raise set_error

    def move(self, pid: int) -> None:
        assert children[-1].poll() is None, "the process to move must still be running"
        moved.append(pid)
        if move_error is not None:
            raise move_error

    monkeypatch.setattr(sys.modules[__name__], "_cfs_cgroup_parent", lambda: ("v2", parent))
    monkeypatch.setattr(CfsQuota, "_set_quota", set_quota)
    monkeypatch.setattr(CfsQuota, "_move", move)
    monkeypatch.setattr(subprocess, "Popen", popen)
    quota, reason = CfsQuota.probe()
    return quota, reason, moved, children


def test_probe_is_unavailable_when_a_process_cannot_be_moved_into_the_group(monkeypatch, tmp_path):
    refused = OSError(95, "Operation not supported")
    quota, reason, moved, children = _probe_on_a_stand_in(monkeypatch, tmp_path, move_error=refused)
    assert quota is None
    assert reason.startswith("cannot move a process into a cgroup with a CFS quota under ")
    assert "Operation not supported" in reason
    assert moved == [children[0].pid] and moved[0] != os.getpid()  # a throwaway child, never the test process
    assert len(children) == 1 and children[0].poll() is not None, "the throwaway child was left running"
    assert list(tmp_path.iterdir()) == [], "the probe left its group behind"


def test_probe_is_available_after_moving_a_throwaway_child(monkeypatch, tmp_path):
    quota, reason, moved, children = _probe_on_a_stand_in(monkeypatch, tmp_path)
    assert isinstance(quota, CfsQuota) and reason == ""
    assert moved == [children[0].pid] and moved[0] != os.getpid()
    assert len(children) == 1 and children[0].poll() is not None
    assert list(tmp_path.iterdir()) == []


def test_probe_starts_no_child_when_the_quota_cannot_be_set(monkeypatch, tmp_path):
    quota, reason, moved, children = _probe_on_a_stand_in(monkeypatch, tmp_path,
                                                          set_error=PermissionError(13, "Permission denied"))
    assert quota is None
    assert reason.startswith("cannot create a cgroup with a CFS quota under ")
    assert moved == [] and children == []
    assert list(tmp_path.iterdir()) == []


def test_the_process_is_moved_by_writing_its_id_to_cgroup_procs(tmp_path):
    q = CfsQuota("v2", tmp_path)
    q.dir.mkdir()
    q._move(4321)
    assert (q.dir / "cgroup.procs").read_text() == "4321"


@pytest.mark.parametrize("route", ROUTES)
def test_health_in_budget_during_whole_ledger_request_cfs_quota(route, ledgers, tmp_path):
    quota, reason = CfsQuota.probe()
    if quota is None:
        pytest.skip(f"SKIPPED, not passed: cannot apply a CFS quota here - {reason}")
    res = _run_under_load(ledgers(SIZES[("cfs-quota", route)]), tmp_path, route, quota=quota)
    assert res["throttled"], "the CFS quota never throttled the ledger process: the limit was not in force"
    _check(res, route, "cfs-quota 1/16 CPU")


@pytest.mark.parametrize("route", ROUTES)
def test_health_in_budget_during_whole_ledger_request_one_core_pin(route, ledgers, tmp_path):
    cpu, reason = _pin_cpu()
    if cpu is None:
        pytest.skip(f"SKIPPED, not passed: cannot pin the ledger to one core here - {reason}")
    res = _run_under_load(ledgers(SIZES[("one-core-pin", route)]), tmp_path, route, pin=cpu)
    _check(res, route, f"one-core-pin cpu{cpu}")
