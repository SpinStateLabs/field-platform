"""Phase G C-6 follow-up, end to end: the REAL ``ledger serve`` process with the
observer switched on, reading REAL HTTP ``/health`` answers from a stub server.

The estates set FIELD_LEDGER_OBSERVE_EVERY=60 and FIELD_LEDGER_OBSERVE_HEALTH to
the seven other operator-block services (``tools/tests/test_ledger_observer_estates_c6.py``
pins that). Here the ledger runs as a subprocess with the GB10 compose file's
own FIELD_LEDGER_OBSERVE_HEALTH names, each pointed at a path on one local stub
server, and the interval at the 5 s floor (60 s would make the test wait a
minute per tick; the interval is the only difference). It shows:

1. at the first observation, one ``operator.mode_changed`` and one
   ``operator.registry_changed`` row per service (``startup: true``), the
   ledger's own block included (8 services);
2. when one service's mode changes, exactly one more ``operator.mode_changed``
   row, naming the previous mode (``startup: false``), and when its registry
   file changes, one more ``operator.registry_changed`` row;
3. the observer's GETs carry no header: no perimeter secret, no operator pair.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
WAIT_S = max(60.0, float(os.environ.get("FIELD_TEST_HARNESS_WAIT") or 0))
SHA_A = "0123456789abcdef"
SHA_B = "fedcba9876543210"


def _compose_targets() -> list[str]:
    """The names in the base compose file's ledger FIELD_LEDGER_OBSERVE_HEALTH."""
    doc = yaml.safe_load((REPO / "integration" / "demo" / "docker-compose.yml").read_text(encoding="utf-8"))
    raw = doc["services"]["ledger"]["environment"]["FIELD_LEDGER_OBSERVE_HEALTH"]
    return [part.split("=", 1)[0] for part in raw.split(",")]


class Stub:
    """Serves ``GET /<name>/health`` from ``self.health[name]``; records each request's headers."""

    def __init__(self, names: list[str]):
        self.health = {n: {"ok": True, "operator_mode": "off", "operator_registry_sha256_prefix": None,
                           "operator_registry_rows": None} for n in names}
        self.requests: list[tuple[str, dict]] = []
        self.lock = threading.Lock()
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):  # noqa: N802
                name, _, rest = self.path.strip("/").partition("/")
                with stub.lock:
                    stub.requests.append((self.path, {k.lower(): v for k, v in self.headers.items()}))
                    body = stub.health.get(name) if rest == "health" else None
                raw = json.dumps(body).encode()
                self.send_response(200 if body is not None else 404)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def set(self, name: str, **fields) -> None:
        with self.lock:
            self.health[name] = {**self.health[name], **fields}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _get(url: str):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return json.loads(resp.read())


@pytest.fixture()
def estate(tmp_path):
    names = _compose_targets()
    stub = Stub(names)
    port = _free_port()
    env = {k: v for k, v in os.environ.items() if not k.startswith("FIELD_")}
    env.update(FIELD_DATA_DIR=str(tmp_path / "data"), FIELD_LEDGER_OBSERVE_EVERY="5",
               FIELD_LEDGER_OBSERVE_HEALTH=",".join(f"{n}={stub.base}/{n}" for n in names))
    proc = subprocess.Popen([sys.executable, "-m", "sealed_ledger.cli", "serve", "--host", "127.0.0.1",
                             "--port", str(port)], env=env, cwd=str(tmp_path),
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + WAIT_S
        while True:
            if proc.poll() is not None:
                raise RuntimeError(f"ledger serve exited early: {proc.returncode}")
            try:
                _get(f"{base}/health")
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError("ledger serve did not come up")
                time.sleep(0.2)
        yield base, stub, names
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
        stub.server.shutdown()


CHECK_ROWS = REPO / "integration" / "demo" / "fixtures" / "c6-observer" / "check_rows.py"


def _check_rows(ledger: str, *args: str) -> int:
    env = {k: v for k, v in os.environ.items() if not k.startswith("FIELD_")}
    return subprocess.run([sys.executable, str(CHECK_ROWS), ledger, *args], env=env,
                          capture_output=True, timeout=120).returncode


def _events(base: str, event_type: str) -> list[dict]:
    return _get(f"{base}/events?event_type={event_type}")


def _wait_for(base: str, event_type: str, count: int) -> list[dict]:
    deadline = time.monotonic() + WAIT_S
    while True:
        evs = _events(base, event_type)
        if len(evs) >= count or time.monotonic() > deadline:
            return evs
        time.sleep(0.25)


def test_the_served_observer_ledgers_the_first_observation_and_each_change(estate):
    base, stub, names = estate
    assert len(names) == 7 and "sealed-ledger" not in names
    services = sorted([*names, "sealed-ledger"])

    # 1. first observation: one of each per service, the ledger's own block included
    modes = _wait_for(base, "operator.mode_changed", len(services))
    regs = _wait_for(base, "operator.registry_changed", len(services))
    assert sorted(e["payload"]["service"] for e in modes) == services, modes
    assert sorted(e["payload"]["service"] for e in regs) == services, regs
    for e in modes:
        assert e["payload"] == {"service": e["payload"]["service"], "mode": "off", "previous_mode": None,
                                "startup": True, "observed_from": "health"}, e
        assert e["agent_id"] is None
    assert all(e["payload"]["startup"] is True and e["payload"]["registry_sha256_prefix"] is None
               for e in regs), regs

    # the CI smoke jobs' check script agrees on this real ledger, and fails on a wrong one
    assert _check_rows(base, "--wait", "0") == 0
    assert _check_rows(base, "--wait", "0", "--mode", "enforce") == 1        # wrong mode
    assert _check_rows(stub.base, "--wait", "0") == 1                        # no rows at all

    # an unchanged estate writes nothing on the next tick
    seen = len(stub.requests)
    deadline = time.monotonic() + WAIT_S
    while len(stub.requests) < seen + len(names) and time.monotonic() < deadline:
        time.sleep(0.25)
    assert len(stub.requests) >= seen + len(names)                    # a second tick has run
    assert len(_events(base, "operator.mode_changed")) == len(services)
    assert len(_events(base, "operator.registry_changed")) == len(services)

    # 2. a mode change (a disarm by host access looks the same, the other way round)
    stub.set("kill-switch", operator_mode="log-only", operator_registry_sha256_prefix=SHA_A,
             operator_registry_rows=10)
    modes = _wait_for(base, "operator.mode_changed", len(services) + 1)
    assert len(modes) == len(services) + 1, modes
    assert modes[-1]["payload"] == {"service": "kill-switch", "mode": "log-only", "previous_mode": "off",
                                    "startup": False, "observed_from": "health"}
    regs = _wait_for(base, "operator.registry_changed", len(services) + 1)
    assert regs[-1]["payload"]["service"] == "kill-switch"
    assert (regs[-1]["payload"]["registry_sha256_prefix"], regs[-1]["payload"]["registry_rows"]) == (SHA_A, 10)
    assert regs[-1]["payload"]["startup"] is False

    #    a registry rollback (same mode, another file): one registry_changed, no mode row
    stub.set("kill-switch", operator_registry_sha256_prefix=SHA_B)
    regs = _wait_for(base, "operator.registry_changed", len(services) + 2)
    assert len(regs) == len(services) + 2, regs
    assert regs[-1]["payload"]["previous_registry_sha256_prefix"] == SHA_A
    assert regs[-1]["payload"]["registry_sha256_prefix"] == SHA_B
    assert len(_events(base, "operator.mode_changed")) == len(services) + 1

    assert _get(f"{base}/verify")["ok"] is True

    # 3. no header on any observer GET
    assert stub.requests and all(not ({"x-field-auth", "x-field-operator", "x-field-operator-key"} & set(h))
                                 for _, h in stub.requests), stub.requests
