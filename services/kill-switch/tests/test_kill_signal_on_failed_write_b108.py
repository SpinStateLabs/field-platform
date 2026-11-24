"""B108 (reviewer-R2's reproduction pkill108b): an ACTIVE agent whose registry write fails (registry unreachable or a
non-200, the agent gone (404), or any other exception) must still get its halt signal. The flip did not land, so
the signal is the only stop left. The caller gets an honest error (never a 200 while the agent is active), and a
domain kill still tries every agent. A refusal BEFORE the write (a retired agent) sends nothing."""
from __future__ import annotations

import types

import httpx
import pytest
from fastapi.testclient import TestClient

import kill_switch.api as ks
from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_core.clients import AgentNotRegisteredError, LedgerClient, RegistryClient, RegistryUnreachableError
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

OP = {"operator": "CISO on-call", "reason": "b108"}
HOST = "agent.test"
FAILURES = {
    "unreachable": RegistryUnreachableError("registry returned 500"),
    "404": AgentNotRegisteredError("a2"),
    "generic": ValueError("boom"),
    "timeout": httpx.ReadTimeout("the write may have committed"),   # a timeout a wrapper did not map
}
SINGLE_STATUS = {"unreachable": 502, "404": 404, "generic": 502, "timeout": 502}


class Endpoint:
    def __init__(self):
        self.urls: list[str] = []

    def request(self, method, url, headers=None, timeout=None):
        self.urls.append(url)
        return types.SimpleNamespace(status_code=200)


class FailingWriteFor:
    """The registry client with a2's kill write failing in the given way; every other call passes through."""

    def __init__(self, inner, failure):
        self._inner, self._failure = inner, failure

    def get_agent(self, agent_id):
        return self._inner.get_agent(agent_id)

    def list_agents(self, **kw):
        return self._inner.list_agents(**kw)

    def set_status(self, agent_id, status, **kw):
        if agent_id == "a2" and status == "killed":
            raise self._failure
        return self._inner.set_status(agent_id, status, **kw)


@pytest.fixture()
def build(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_KILL_ENDPOINT_ALLOWLIST", HOST)
    manifest = types.SimpleNamespace(enforcement=types.SimpleNamespace(
        kill_switch=types.SimpleNamespace(endpoint=f"http://{HOST}/halt", method="POST")))
    monkeypatch.setattr(ks, "resolve_manifest_detail", lambda ref, *a, **k: (manifest, "ok"))

    def make(agent_ids, failure):
        registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "agents.sqlite3")))
        ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "events.jsonl")))
        for agent_id in agent_ids:
            assert registry.post("/agents", json={"agent_id": agent_id, "name": agent_id, "owner": "O",
                                                  "domain": "finance"}).status_code == 201
        endpoint = Endpoint()
        kill = TestClient(ks.create_app(
            registry=FailingWriteFor(RegistryClient(client=registry, base_url="http://t"), failure),
            ledger=LedgerClient(client=ledger, base_url="http://t"), endpoint_client=endpoint),
            raise_server_exceptions=False)
        return types.SimpleNamespace(registry=registry, ledger=ledger, kill=kill, endpoint=endpoint)

    return make


def _status(stack, agent_id):
    return stack.registry.get(f"/agents/{agent_id}").json()["status"]


def _events(stack, event_type):
    return stack.ledger.get("/events", params={"event_type": event_type}).json()


def _signalled(stack):
    return sorted(e["agent_id"] for e in _events(stack, "kill.endpoint_called"))


def _failed(stack):
    return sorted(e["agent_id"] for e in _events(stack, "kill.agent.failed"))


@pytest.mark.parametrize("case", sorted(FAILURES))
def test_single_kill_with_a_failed_write_still_signals_and_answers_an_error(build, case):
    stack = build(["a2"], FAILURES[case])
    r = stack.kill.post("/kill/a2", json=OP)
    assert r.status_code == SINGLE_STATUS[case], r.text      # honest: never 200 while the agent is still active
    assert _status(stack, "a2") == "active"
    assert len(stack.endpoint.urls) == 1                      # the halt signal went out anyway
    assert _signalled(stack) == ["a2"]
    assert _failed(stack) == ["a2"]                           # the failed kill is still ledgered as one


@pytest.mark.parametrize("case", sorted(FAILURES))
def test_domain_kill_with_one_failed_write_signals_it_and_still_kills_the_rest(build, case):
    stack = build(["a1", "a2", "a3"], FAILURES[case])
    r = stack.kill.post("/kill/domain/finance", json=OP)
    assert r.status_code == 502, r.text                       # one agent errored: the route is not 2xx
    report = r.json()["detail"]
    outcomes = {row["agent_id"]: row["outcome"] for row in report["results"]}
    assert outcomes == {"a1": "killed", "a2": "error", "a3": "killed"}
    assert [_status(stack, a) for a in ("a1", "a2", "a3")] == ["killed", "active", "killed"]
    assert len(stack.endpoint.urls) == 3                      # every agent signalled, a2 included
    assert _signalled(stack) == ["a1", "a2", "a3"]
    assert _failed(stack) == ["a2"]


def test_a_refusal_before_the_write_still_sends_nothing(build):
    """A retired agent is refused (409) before any write: no write failure, so no signal."""
    stack = build(["a2"], RuntimeError("never raised"))
    RegistryClient(client=stack.registry, base_url="http://t").set_status("a2", "retired")
    r = stack.kill.post("/kill/a2", json=OP)
    assert r.status_code == 409
    assert stack.endpoint.urls == [] and _signalled(stack) == []


def test_control_a_working_write_kills_signals_and_answers_200(build):
    stack = build(["a1"], RuntimeError("never raised"))           # only a2's write fails
    r = stack.kill.post("/kill/a1", json=OP)
    assert r.status_code == 200 and _status(stack, "a1") == "killed"
    assert _signalled(stack) == ["a1"] and _failed(stack) == []


def test_control_a_domain_with_no_failure_answers_200_and_signals_all(build):
    stack = build(["a1", "a3"], RuntimeError("never raised"))      # a2 absent: no write fails
    r = stack.kill.post("/kill/domain/finance", json=OP)
    assert r.status_code == 200
    assert _signalled(stack) == ["a1", "a3"] and _failed(stack) == []
