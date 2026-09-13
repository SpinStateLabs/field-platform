"""C2 latency at 100,000 events (build spec §6.5; plan Phase C build item J16).

- ``test_health_is_o1_at_100k_events`` (always runs): ``/health`` answers from
  a cache — in process and over real HTTP — in under 50 ms at 100k events.
- ``test_served_latency_100k_under_verify_readers_and_rotation`` (the full
  §6.5 run: a real ``ledger serve`` subprocess, ~2 minutes; runs only with
  FIELD_SLOW_TESTS=1): L1 ``/health`` < 2.0 s while ``/verify`` runs; L2
  appends < 5.0 s with 4 ``/verify`` in flight; L3 the same plus a
  ``POST /rotate`` of the 100k open segment; final ``/verify`` ok with
  ``length == /health.event_count == 100,000 + acked appends + rotations``.
  The build spec requires the pass on the 20-core Linux shape; a Windows
  laptop is a slower, noisier host.

Every phase prints its maxima.
"""

from __future__ import annotations

import http.client
import json
import os
import shutil
import socket
import statistics
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from ledger_c2_support import KEY_PRIV, SLOW
from field_core.ledger import make_event
from sealed_ledger.store import LedgerStore

N = 100_000


@pytest.fixture(scope="module")
def fixture_100k(tmp_path_factory) -> Path:
    """100,000 events (~53 MB): payload {i, tool, pad: 200 x 'x'}, 7 agents."""
    p = tmp_path_factory.mktemp("c2-100k") / "fixture.jsonl"
    prev = "0" * 64
    with open(p, "w", encoding="utf-8") as fh:
        for i in range(N):
            e = make_event("action", {"i": i, "tool": "t", "pad": "x" * 200}, prev_hash=prev,
                           agent_id=f"agent-{i % 7}")
            fh.write(e.model_dump_json() + "\n")
            prev = e.hash
    return p


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _req(port: int, method: str, path: str, body=None, timeout: float = 5.0):
    t0 = time.monotonic()
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
        headers = {"content-type": "application/json"} if body is not None else {}
        conn.request(method, path, body=json.dumps(body) if body is not None else None, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return time.monotonic() - t0, resp.status, data
    except Exception as exc:  # noqa: BLE001
        return time.monotonic() - t0, type(exc).__name__, b""


def test_health_is_o1_at_100k_events(fixture_100k, tmp_path):
    import uvicorn

    from sealed_ledger.api import create_app

    p = tmp_path / "ledger" / "events.jsonl"
    p.parent.mkdir()
    shutil.copyfile(fixture_100k, p)
    store = LedgerStore(p)
    for _ in range(5):
        store.health_info()
    direct = []
    for _ in range(200):
        t0 = time.perf_counter()
        info = store.health_info()
        direct.append((time.perf_counter() - t0) * 1000)
    assert info["event_count"] == N

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(store=store), log_level="warning"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 30
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        for _ in range(5):
            _req(port, "GET", "/health", timeout=2.0)
        served = []
        for _ in range(100):  # a new connection per request, as the sentinel does
            dt, status, data = _req(port, "GET", "/health", timeout=2.0)
            assert status == 200
            served.append(dt * 1000)
        assert json.loads(data)["event_count"] == N
        store.append("after", {})
        dt, status, data = _req(port, "GET", "/health", timeout=2.0)
        assert json.loads(data)["event_count"] == N + 1
    finally:
        server.should_exit = True
        thread.join(30)
    served.sort()
    p95 = served[int(len(served) * 0.95) - 1]
    print(f"\nJ16 /health at {N} events: in-process max {max(direct):.3f} ms "
          f"(median {statistics.median(direct):.3f}); HTTP median {statistics.median(served):.1f} ms, "
          f"p95 {p95:.1f} ms, max {served[-1]:.1f} ms")
    assert max(direct) < 50.0
    assert p95 < 50.0


def test_health_stays_o1_at_100k_while_this_process_appends(fixture_100k, tmp_path):
    """J16 under this process's own writes (C2 review C2PD-2): 4 threads append
    to the SAME store while /health is sampled. An append in flight (written,
    not yet in the cache) is not another process's write, so /health never
    re-counts the 100k open segment for it."""
    p = tmp_path / "ledger" / "events.jsonl"
    p.parent.mkdir()
    shutil.copyfile(fixture_100k, p)
    store = LedgerStore(p)
    recounts: list = []
    real = LedgerStore._take_snapshot
    store._take_snapshot = lambda *a, **k: recounts.append(k) or real(store, *a, **k)
    stop = threading.Event()
    acks = [0]
    lock = threading.Lock()

    def writer():
        while not stop.is_set():
            store.append("storm", {"pad": "y" * 200})
            with lock:
                acks[0] += 1

    threads = [threading.Thread(target=writer) for _ in range(4)]
    for t in threads:
        t.start()
    samples = []
    try:
        end = time.monotonic() + 5.0
        while time.monotonic() < end:
            t0 = time.perf_counter()
            store.health_info()
            samples.append((time.perf_counter() - t0) * 1000)
            time.sleep(0.01)
    finally:
        stop.set()
        for t in threads:
            t.join(60)
    samples.sort()
    p95 = samples[int(len(samples) * 0.95) - 1]
    print(f"\nJ16 under in-process appends: {len(samples)} samples, {acks[0]} appends, "
          f"p95 {p95:.2f} ms, max {samples[-1]:.2f} ms, out-of-band recounts {len(recounts)}")
    assert acks[0] > 0 and recounts == []
    assert p95 < 50.0
    assert store.health_info()["event_count"] == N + acks[0]


@pytest.mark.skipif(not SLOW, reason="full §6.5 served run (~2 min): set FIELD_SLOW_TESTS=1")
def test_served_latency_100k_under_verify_readers_and_rotation(fixture_100k, tmp_path):
    work = tmp_path / "data"
    (work / "ledger").mkdir(parents=True)
    shutil.copyfile(fixture_100k, work / "ledger" / "events.jsonl")
    key = tmp_path / "keys" / "anchor.pem"  # written only after the first /rotate (see below)
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if k not in ("FIELD_SHARED_SECRET", "FIELD_LEDGER_URL")}
    env.update(FIELD_DATA_DIR=str(work), FIELD_LEDGER_ANCHOR_KEY=str(key), PYTHONIOENCODING="utf-8")
    log = open(tmp_path / "server.log", "w", encoding="utf-8")
    srv = subprocess.Popen([sys.executable, "-m", "sealed_ledger.cli", "serve", "--port", str(port)],
                           env=env, stdout=log, stderr=subprocess.STDOUT)
    out: dict = {"python": sys.version.split()[0], "os": os.name}
    try:
        deadline = time.monotonic() + 180
        while time.monotonic() < deadline:
            _, status, _ = _req(port, "GET", "/health", timeout=2.0)
            if status == 200:
                break
            assert srv.poll() is None, (tmp_path / "server.log").read_text()[-2000:]
            time.sleep(0.5)
        # a key that cannot be loaded is a 503, never a process exit
        _, status, data = _req(port, "POST", "/rotate", {"operator": "latency", "reason": "c2"}, timeout=30)
        assert status == 503 and b"anchor key unreadable" in data, data
        assert srv.poll() is None
        key.parent.mkdir()
        key.write_text(KEY_PRIV, encoding="ascii")

        dt, status, data = _req(port, "GET", "/verify", timeout=300)
        assert status == 200 and json.loads(data)["ok"]
        out["verify_alone_s"] = round(dt, 3)

        # L1: /health every 50 ms while 3 consecutive /verify run
        spans: list = []

        def verifier():
            for _ in range(3):
                t0 = time.monotonic()
                _, s2, _ = _req(port, "GET", "/verify", timeout=300)
                spans.append((t0, time.monotonic(), s2))

        th = threading.Thread(target=verifier)
        th.start()
        samples = []
        while th.is_alive():
            t0 = time.monotonic()
            dt, status, _ = _req(port, "GET", "/health", timeout=2.0)
            samples.append((t0, t0 + dt, dt, status))
            time.sleep(0.05)
        th.join()
        overlapping = [s for s in samples if any(a <= s[0] and s[1] <= b for a, b, _ in spans)]
        out["L1_samples"] = len(overlapping)
        out["L1_health_max_s"] = round(max((s[2] for s in overlapping), default=0), 3)
        assert overlapping and all(s[3] == 200 for s in overlapping)
        assert all(sp[2] == 200 for sp in spans)

        acked = 0
        rotations = 0

        def phase(rotate: bool, seconds: float) -> dict:
            nonlocal acked, rotations
            stop = threading.Event()
            active = [0]
            lock = threading.Lock()
            marks: list = []
            verifies: list = []

            def vloop():
                while not stop.is_set():
                    with lock:
                        active[0] += 1
                        marks.append((time.monotonic(), active[0]))
                    d2, s2, _ = _req(port, "GET", "/verify", timeout=300)
                    with lock:
                        active[0] -= 1
                        marks.append((time.monotonic(), active[0]))
                    verifies.append((d2, s2))

            threads = [threading.Thread(target=vloop, daemon=True) for _ in range(4)]
            for t in threads:
                t.start()
            time.sleep(1.0)
            appends, health, rot = [], [], {}
            t_stop = time.monotonic() + seconds
            rotated = False
            nxt = time.monotonic()
            while time.monotonic() < t_stop:
                if rotate and not rotated and time.monotonic() > t_stop - seconds + 2.0:
                    rotated = True

                    def do_rotate():
                        d3, s3, body = _req(port, "POST", "/rotate",
                                            {"operator": "latency", "reason": "c2"}, timeout=300)
                        rot.update(s=round(d3, 3), status=s3)

                    threading.Thread(target=do_rotate, daemon=True).start()
                t0 = time.monotonic()
                with lock:
                    a0 = active[0]
                dt, status, _ = _req(port, "POST", "/events",
                                     {"event_type": "latency", "agent_id": "j", "payload": {}}, timeout=5.0)
                with lock:
                    full = a0 == 4 and active[0] == 4 and all(m[1] >= 4 for m in marks if t0 <= m[0] <= t0 + dt)
                appends.append((dt, status, full))
                if status == 201:
                    acked += 1
                if rotate:
                    d4, s4, _ = _req(port, "GET", "/health", timeout=2.0)
                    health.append((d4, s4))
                nxt += 0.1
                time.sleep(max(0.0, nxt - time.monotonic()))
            stop.set()
            for t in threads:
                t.join(300)
            deadline2 = time.monotonic() + 120
            while rotate and "status" not in rot and time.monotonic() < deadline2:
                time.sleep(0.1)
            in_flight = [a for a in appends if a[2]]
            res = {
                "appends": len(appends), "appends_with_4_verify_in_flight": len(in_flight),
                "append_max_s_4_in_flight": round(max((a[0] for a in in_flight), default=0), 3),
                "append_max_s_all": round(max((a[0] for a in appends), default=0), 3),
                "append_failures": sum(1 for a in appends if a[1] != 201),
                "verify_calls": len(verifies), "verify_non_200": sum(1 for v in verifies if v[1] != 200),
            }
            if rotate:
                res["rotate"] = rot
                res["health_max_s"] = round(max((h[0] for h in health), default=0), 3)
                res["health_failures"] = sum(1 for h in health if h[1] != 200)
                if rot.get("status") == 200:
                    rotations += 1
            return res

        out["L2"] = phase(False, 30.0)
        out["L3"] = phase(True, 30.0)
        dt, status, data = _req(port, "GET", "/verify", timeout=300)
        final = json.loads(data)
        _, _, hdata = _req(port, "GET", "/health", timeout=2.0)
        out["final_verify"] = {k: final.get(k) for k in ("ok", "length", "segments")}
        out["final_health_count"] = json.loads(hdata)["event_count"]
    finally:
        srv.terminate()
        try:
            srv.wait(30)
        except subprocess.TimeoutExpired:
            srv.kill()
        log.close()
    print("\n§6.5 latency at 100k:", json.dumps(out, indent=1))
    assert out["L1_health_max_s"] < 2.0
    for name in ("L2", "L3"):
        assert out[name]["append_failures"] == 0 and out[name]["verify_non_200"] == 0, out[name]
        assert out[name]["appends_with_4_verify_in_flight"] > 0, out[name]
        assert out[name]["append_max_s_4_in_flight"] < 5.0, out[name]
    assert out["L3"]["rotate"].get("status") == 200, out["L3"]
    assert out["L3"]["health_max_s"] < 2.0 and out["L3"]["health_failures"] == 0
    assert final["ok"] and final["segments"] == 2
    assert final["length"] == out["final_health_count"] == N + acked + rotations
