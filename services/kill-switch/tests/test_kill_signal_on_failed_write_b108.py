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
from field_core import operator_auth
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


def test_a_failed_write_whose_signal_also_fails_answers_the_write_error_and_ledgers_both(build):
    """Review question 2: the write fails AND the halt signal fails. The caller sees the write's error (the signal
    never raises); the ledger holds kill.endpoint_failed (with the signal's reason) and kill.agent.failed."""
    stack = build(["a2"], RegistryUnreachableError("registry returned 500"))

    def refuse(method, url, headers=None, timeout=None):
        stack.endpoint.urls.append(url)
        raise ConnectionError("endpoint down")

    stack.endpoint.request = refuse
    r = stack.kill.post("/kill/a2", json=OP)
    assert r.status_code == 502 and "registry unreachable" in r.json()["detail"]
    assert len(stack.endpoint.urls) == 1                      # the signal was attempted
    failed_signal = _events(stack, "kill.endpoint_failed")
    assert [e["agent_id"] for e in failed_signal] == ["a2"]
    assert failed_signal[0]["payload"]["reason"] == "transport_error"
    assert _signalled(stack) == [] and _failed(stack) == ["a2"]


# --- review conditions (R2 and the second reviewer) ------------------------------------------------------------------


def _registry_answering(status: int):
    """The exception the REAL RegistryClient raises when the registry answers the kill PATCH with `status`."""
    client = RegistryClient(client=httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(status, json={"detail": "refused"}))), base_url="http://t")
    try:
        client.set_status("a2", "killed")
    except Exception as exc:      # noqa: BLE001
        return exc
    raise AssertionError("no exception")


@pytest.mark.parametrize("status", [401, 403])
def test_a_registry_auth_refusal_on_the_write_still_signals(build, status):
    exc = _registry_answering(status)
    assert isinstance(exc, RegistryUnreachableError)
    stack = build(["a2"], exc)
    r = stack.kill.post("/kill/a2", json=OP)
    assert r.status_code == 502 and _status(stack, "a2") == "active"
    assert _signalled(stack) == ["a2"] and _failed(stack) == ["a2"]


def test_an_exception_in_the_signal_path_never_replaces_the_write_error(build, monkeypatch):
    stack = build(["a2"], RegistryUnreachableError("registry returned 500"))

    def broken(ref, *a, **k):
        raise RuntimeError("manifest resolution blew up")

    monkeypatch.setattr(ks, "resolve_manifest_detail", broken)
    r = stack.kill.post("/kill/a2", json=OP)
    assert r.status_code == 502 and "registry unreachable" in r.json()["detail"]     # the write's error, not a 500
    failed_kill = _events(stack, "kill.agent.failed")
    assert [e["payload"]["failure_class"] for e in failed_kill] == ["registry_failure"]
    failed_signal = _events(stack, "kill.endpoint_failed")
    assert [(e["agent_id"], e["payload"]["reason"]) for e in failed_signal] == [("a2", "signal_error")]
    assert "blew up" not in str(failed_signal) and "error" not in failed_signal[0]["payload"]   # fixed text only


def test_an_operator_refusal_before_the_write_sends_nothing(build, monkeypatch):
    stack = build(["a2"], RuntimeError("never raised"))

    def refuse(auth, manifest_ref):
        raise operator_auth.OperatorRefused(403, "operator not authorized for this agent")

    monkeypatch.setattr(operator_auth, "check_record_authorized", refuse)
    r = stack.kill.post("/kill/a2", json=OP)
    assert r.status_code == 403
    assert _status(stack, "a2") == "active"
    assert stack.endpoint.urls == [] and _signalled(stack) == [] and _events(stack, "kill.endpoint_failed") == []


def test_a_404_on_the_read_sends_nothing(build):
    stack = build([], RuntimeError("never raised"))
    r = stack.kill.post("/kill/ghost-agent", json=OP)
    assert r.status_code == 404
    assert stack.endpoint.urls == [] and _signalled(stack) == [] and _events(stack, "kill.endpoint_failed") == []
