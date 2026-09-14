"""v1.2 X3: the canary agent's real halt endpoint, and the kill-switch calling it.

Three layers, each with a test that fails if the property is removed:

* the endpoint alone (a real socket, in-process): the origin header is
  required, the 200 echoes the nonce from the kill reason, ``/status``
  reflects the halt, and a halt stops the work loop;
* the process (a real ``python -m field_agent.canary serve`` subprocess): it
  NEVER exits on a halt and keeps serving;
* the real kill-switch app calling the real endpoint over a real socket with
  the REAL ``canary-gb10`` manifest (``http://canary-agent:8090/halt``) and
  ``FIELD_KILL_ENDPOINT_ALLOWLIST=canary-agent``: kill with ``x3-<nonce>`` =>
  ``called`` AND ``/status`` halted with the same nonce; revive recorded; drill
  on the ``canary``-domain record => ``endpoint_confirmed_ms`` present. The ONE
  substitution is name resolution: ``canary-agent:8090`` is dialled as
  ``127.0.0.1:<port>`` (compose DNS does that on the GB10). Method, headers,
  timeout and the ``follow_redirects=False`` client are the kill-switch's own.
"""

from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote, urlsplit, urlunsplit

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_agent import canary as canary_mod
from field_agent.canary import ORIGIN_HEADER, ORIGIN_VALUE, REASON_HEADER, CanaryAgent, CanaryState, parse_nonce
from field_core.clients import LedgerClient, RegistryClient
from kill_switch.api import create_app as create_kill_app, new_endpoint_client
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

REPO = Path(__file__).resolve().parents[3]
CANARY_MANIFEST = REPO / "manifests" / "canary-gb10.yaml"
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http(method: str, url: str, headers: dict | None = None, body: dict | None = None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=dict(headers or {}))
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with OPENER.open(req, timeout=5) as resp:
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"null")


KILL = {ORIGIN_HEADER: ORIGIN_VALUE}


@pytest.fixture(autouse=True)
def _no_secret_no_allowlist(monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    monkeypatch.delenv("FIELD_KILL_ENDPOINT_ALLOWLIST", raising=False)
    monkeypatch.delenv("FIELD_MANIFEST_DIR", raising=False)


@pytest.fixture()
def running():
    agent = CanaryAgent("canary-gb10", host="127.0.0.1", port=0, work_every=0.01)
    thread = threading.Thread(target=agent.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{agent.port}"
    try:
        yield SimpleNamespace(agent=agent, base=base)
    finally:
        agent.shutdown()
        thread.join(timeout=5)


def _wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


# --- the endpoint ------------------------------------------------------------------


def test_parse_nonce_takes_the_x3_token_and_nothing_else():
    assert parse_nonce("x3-4f2a9c") == "4f2a9c"
    assert parse_nonce("gate check x3-ab_cd-01 by Don") == "ab_cd-01"
    assert parse_nonce("anomalous behavior") is None
    assert parse_nonce("notx3-abc") is None           # bounded: not a suffix match
    assert parse_nonce(None) is None


def test_halt_echoes_the_nonce_from_the_kill_reason(running):
    status, body = http("POST", f"{running.base}/halt", {**KILL, REASON_HEADER: "x3-4f2a9c"})
    assert status == 200
    assert body["halted"] is True and body["nonce"] == "4f2a9c" and body["agent_id"] == "canary-gb10"
    # percent-encoded, as the kill-switch sends it
    status, body = http("POST", f"{running.base}/halt",
                        {**KILL, REASON_HEADER: quote("gate check x3-9e8d7c now", safe="")})
    assert status == 200 and body["nonce"] == "9e8d7c"
    # a JSON body reason when the header is absent (manual use)
    status, body = http("POST", f"{running.base}/halt", KILL, body={"reason": "x3-body01"})
    assert status == 200 and body["nonce"] == "body01"


def test_halt_requires_the_origin_header(running):
    for headers in ({}, {ORIGIN_HEADER: "someone-else"}, {REASON_HEADER: "x3-nope"}):
        status, body = http("POST", f"{running.base}/halt", headers)
        assert status == 403, headers
        assert body["halted"] is False
    _, snap = http("GET", f"{running.base}/status")
    assert snap["halted"] is False and snap["halts"] == 0 and snap["nonce"] is None
    ticks = snap["work_ticks"]
    assert _wait_for(lambda: http("GET", f"{running.base}/status")[1]["work_ticks"] > ticks), \
        "a refused halt must not stop the work"


def test_status_reflects_the_latest_nonce_and_the_first_halt_time(running):
    status, snap = http("GET", f"{running.base}/status")
    assert status == 200
    assert (snap["halted"], snap["nonce"], snap["since"], snap["halts"]) == (False, None, None, 0)

    http("POST", f"{running.base}/halt", {**KILL, REASON_HEADER: "x3-first"})
    first = http("GET", f"{running.base}/status")[1]
    assert first["halted"] is True and first["nonce"] == "first" and first["since"]
    assert first["last_halted_by"] == "endpoint" and first["halts"] == 1

    http("POST", f"{running.base}/halt", {**KILL, REASON_HEADER: "x3-second"})
    second = http("GET", f"{running.base}/status")[1]
    assert second["nonce"] == "second" and second["since"] == first["since"] and second["halts"] == 2

    http("POST", f"{running.base}/halt", {**KILL, REASON_HEADER: "no nonce here"})
    third = http("GET", f"{running.base}/status")[1]
    assert third["halted"] is True and third["nonce"] is None and third["halts"] == 3


def test_a_halt_stops_the_work_loop(running):
    assert _wait_for(lambda: running.agent.state.work_ticks > 3)
    status, _ = http("POST", f"{running.base}/halt", {**KILL, REASON_HEADER: "x3-stop"})
    assert status == 200
    frozen = running.agent.state.work_ticks
    time.sleep(0.3)                                    # ~30 work intervals
    assert running.agent.state.work_ticks == frozen
    assert running.agent.state.tick() is False


def test_unknown_routes_and_methods_do_not_halt(running):
    assert http("GET", f"{running.base}/halt")[0] == 405
    assert http("POST", f"{running.base}/status", KILL)[0] == 405
    assert http("POST", f"{running.base}/kill", KILL)[0] == 404
    status, health = http("GET", f"{running.base}/health")
    assert status == 200 and health["service"] == "canary-agent"
    assert http("GET", f"{running.base}/status")[1]["halted"] is False


# --- the process never exits -------------------------------------------------------


def test_the_process_never_exits_on_a_halt(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in ("FIELD_SHARED_SECRET", "FIELD_CANARY_HEARTBEAT_EVERY")}
    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "field_agent.canary", "serve", "--agent-id", "canary-gb10",
         "--host", "127.0.0.1", "--port", "0", "--work-every", "0.05"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=str(tmp_path), text=True,
    )
    lines: queue.Queue[str] = queue.Queue()
    threading.Thread(target=lambda: [lines.put(line) for line in proc.stdout], daemon=True).start()
    try:
        first = lines.get(timeout=30)
        assert "listening on 127.0.0.1:" in first, first
        base = "http://127.0.0.1:" + first.split("listening on 127.0.0.1:")[1].split()[0]

        status, body = http("POST", f"{base}/halt", {**KILL, REASON_HEADER: "x3-alive01"})
        assert status == 200 and body["nonce"] == "alive01"
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:             # a process that exits after answering is caught here
            assert proc.poll() is None, "the canary exited after a halt"
            time.sleep(0.1)
        status, snap = http("GET", f"{base}/status")
        assert status == 200 and snap["halted"] is True and snap["nonce"] == "alive01"
        # (no pid comparison: a Windows venv python.exe is a launcher whose child
        # serves; the launcher exits when that child does, so poll() still sees it)
        status, body = http("POST", f"{base}/halt", {**KILL, REASON_HEADER: "x3-alive02"})
        assert status == 200 and body["halts"] == 2
        time.sleep(0.5)
        assert proc.poll() is None
    finally:
        proc.terminate()
        proc.wait(timeout=10)


# --- heartbeat polling -------------------------------------------------------------


class FakeLiveness:
    def __init__(self, answer):
        self.answer, self.calls = answer, 0

    def heartbeat(self, agent_id):
        self.calls += 1
        if isinstance(self.answer, Exception):
            raise self.answer
        return SimpleNamespace(agent_id=agent_id, killed=self.answer)


def test_heartbeat_polling_is_off_by_default_and_never_starts():
    fake = FakeLiveness(True)
    agent = CanaryAgent("canary-gb10", host="127.0.0.1", port=0, work_every=0.01, liveness=fake)
    try:
        assert agent.heartbeat_every == 0 and agent.state.snapshot()["heartbeat_every"] == 0
        agent.start_background()
        time.sleep(0.2)
        assert fake.calls == 0 and agent.state.halted is False
    finally:
        agent.shutdown()


def test_heartbeat_poll_halts_on_killed_and_on_unreachable_without_touching_the_nonce():
    for answer, source in ((True, "heartbeat"), (ConnectionError("down"), "heartbeat_unreachable")):
        agent = CanaryAgent("canary-gb10", host="127.0.0.1", port=0, heartbeat_every=30, liveness=FakeLiveness(answer))
        try:
            agent.state.halt(source="endpoint", nonce="keepme", set_nonce=True)
            agent.poll_heartbeat_once()
            snap = agent.state.snapshot()
            assert snap["halted"] is True and snap["last_halted_by"] == source and snap["nonce"] == "keepme"
        finally:
            agent.shutdown()
    live = CanaryAgent("canary-gb10", host="127.0.0.1", port=0, heartbeat_every=30, liveness=FakeLiveness(False))
    try:
        live.poll_heartbeat_once()
        assert live.state.halted is False
    finally:
        live.shutdown()


# --- the real kill-switch calling the real endpoint --------------------------------


class ResolveCanaryAgent:
    """Compose DNS, and nothing else: ``canary-agent:8090`` -> ``127.0.0.1:<port>``."""

    def __init__(self, inner, port: int):
        self.inner, self.port, self.urls = inner, port, []

    def request(self, method, url, headers=None, timeout=None):
        parts = urlsplit(url)
        assert (parts.hostname, parts.port) == ("canary-agent", 8090), url
        self.urls.append(url)
        return self.inner.request(method, urlunsplit(parts._replace(netloc=f"127.0.0.1:{self.port}")),
                                  headers=headers, timeout=timeout)


class Estate:
    """registry + ledger + the real kill-switch app, and the real canary manifest."""

    def __init__(self, tmp_path: Path, canary_port: int):
        self.registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
        self.ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
        self.endpoint = ResolveCanaryAgent(new_endpoint_client(), canary_port)
        self.kill = TestClient(create_kill_app(
            registry=RegistryClient(client=self.registry, base_url="http://t"),
            ledger=LedgerClient(client=self.ledger, base_url="http://t"),
            endpoint_client=self.endpoint,
        ))
        manifest = tmp_path / "manifests" / "canary-gb10.yaml"
        manifest.parent.mkdir()
        shutil.copyfile(CANARY_MANIFEST, manifest)
        r = self.registry.post("/agents", json={
            "agent_id": "canary-gb10", "name": "canary-gb10", "owner": "FIELD canary",
            "domain": "canary", "manifest_ref": str(manifest)})
        assert r.status_code == 201, r.text

    def count(self, event_type: str) -> int:
        return len(self.ledger.get("/events", params={"event_type": event_type, "agent_id": "canary-gb10"}).json())

    def close(self):
        self.endpoint.inner.close()


@pytest.fixture()
def estate(tmp_path, running):
    e = Estate(tmp_path, running.agent.port)
    try:
        yield e
    finally:
        e.close()


OP = {"operator": "FIELD gate verification (canary)"}


def test_the_shipped_canary_manifest_points_at_the_canary_agent_service():
    text = CANARY_MANIFEST.read_text(encoding="utf-8")
    assert "endpoint: http://canary-agent:8090/halt" in text and "method: HTTP POST" in text


def test_kill_with_a_nonce_calls_the_endpoint_and_the_agent_reports_that_nonce(estate, running, monkeypatch):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", "canary-agent")
    r = estate.kill.post("/kill/canary-gb10", json={**OP, "reason": "x3-5b1e0d7a"})
    assert r.status_code == 200
    result = r.json()["endpoint_result"]
    assert result["outcome"] == "called", result
    assert result["http_status"] == 200 and result["endpoint_host"] == "canary-agent" and result["method"] == "POST"
    assert estate.endpoint.urls == ["http://canary-agent:8090/halt"]
    assert estate.count("kill.endpoint_called") == 1

    status, snap = http("GET", f"{running.base}/status")
    assert status == 200
    assert snap["halted"] is True and snap["nonce"] == "5b1e0d7a" and snap["last_halted_by"] == "endpoint"
    frozen = snap["work_ticks"]

    # revive is recorded; the process stays halted (a revive is a registry flip, not a restart)
    assert estate.kill.post("/revive/canary-gb10", json={**OP, "reason": "x3 revive"}).status_code == 200
    assert estate.count("kill.revive") == 1
    assert estate.kill.get("/heartbeat/canary-gb10").json()["killed"] is False
    time.sleep(0.1)
    after = http("GET", f"{running.base}/status")[1]
    assert after["halted"] is True and after["work_ticks"] == frozen


def test_drill_on_the_canary_domain_record_reports_endpoint_confirmed_ms(estate, running, monkeypatch):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", "canary-agent")
    assert estate.registry.get("/agents/canary-gb10").json()["domain"] == "canary"
    report = estate.kill.post("/drill/canary-gb10", json={**OP, "reason": "x3-d4d4d4"}).json()
    assert report["endpoint_result"]["outcome"] == "called"
    assert isinstance(report["endpoint_confirmed_ms"], float)
    assert report["restored"] is True and report["restored_status"] == "active"
    assert http("GET", f"{running.base}/status")[1]["nonce"] == "d4d4d4"


def test_without_the_allowlist_the_canary_is_never_called(estate, running):
    r = estate.kill.post("/kill/canary-gb10", json={**OP, "reason": "x3-unarmed"})
    result = r.json()["endpoint_result"]
    assert (result["outcome"], result["reason"], result["endpoint_host"]) == (
        "skipped", "allowlist_unset", "canary-agent")
    assert estate.endpoint.urls == []
    snap = http("GET", f"{running.base}/status")[1]
    assert snap["halted"] is False and snap["halts"] == 0


# --- x3-check: the live check itself can fail --------------------------------------


def _platform(estate: Estate):
    clients = {"registry": estate.registry, "ledger": estate.ledger, "killswitch": estate.kill}

    def call(method, url, body=None):
        parts = urlsplit(url)
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        resp = clients[parts.hostname].request(method, path, json=body)
        return resp.status_code, resp.json()
    return call


def _run_check(estate, running, agent="canary-gb10"):
    out: list[str] = []
    code = canary_mod.x3_check(
        agent, killswitch_url="http://killswitch", registry_url="http://registry", ledger_url="http://ledger",
        canary_url="http://canary-agent:8090",
        platform=_platform(estate),
        canary=lambda m, u, b=None: canary_mod.urllib_call(m, u.replace("canary-agent:8090", f"127.0.0.1:{running.agent.port}"), b),
        out=out.append,
    )
    return code, "\n".join(out)


def test_x3_check_passes_on_an_armed_estate(estate, running, monkeypatch):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", "canary-agent")
    code, text = _run_check(estate, running)
    assert code == 0, text
    assert "FAIL" not in text and "checks passed" in text


def test_x3_check_fails_when_the_allowlist_is_unset(estate, running):
    code, text = _run_check(estate, running)
    assert code == 1, text
    assert "[FAIL] kill reason x3-" in text and "outcome=skipped" in text


def test_x3_check_refuses_anything_but_a_canary(estate, running, monkeypatch):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", "canary-agent")
    code, text = _run_check(estate, running, agent="invoicing-agent")
    assert code == 2 and text.startswith("refusing:")
    assert estate.count("kill.agent") == 0 and estate.endpoint.urls == []
