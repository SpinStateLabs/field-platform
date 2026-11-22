"""Kill-path hardening (roley.reviewer URGENT findings, current main):

* F-DRILL: a drill that restores an agent must not undo a REAL kill that landed while it ran (R1 kill after the drill's
  flip, R2 kill between the drill's read and its flip, R3 real threads). The restore is conditional; a superseded
  restore leaves the agent killed and ledgers ``kill.drill.restore_skipped``.
* F-PM405-1: a registry 404 (or any other exception) on the kill PATCH must not abort a domain kill: every agent is
  attempted, each failure is reported as errored, ``kill.domain`` is always written, the route answers non-2xx.
* F-PM405-2: a PATCH that answers 200 but whose body does not say ``killed`` is a failure, never a reported kill.
"""

from __future__ import annotations

import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app as create_registry_app
from agent_registry.store import RegistryStore
from field_core.clients import AgentNotRegisteredError, LedgerClient, RegistryClient, RegistryUnreachableError
from kill_switch.api import create_app as create_kill_app
from sealed_ledger.api import create_app as create_ledger_app
from sealed_ledger.store import LedgerStore

OP = {"operator": "CISO", "reason": "kill-path"}


class Stack:
    def __init__(self, tmp_path, wrap=None):
        self.registry = TestClient(create_registry_app(store=RegistryStore(tmp_path / "a.sqlite3")))
        self.ledger = TestClient(create_ledger_app(store=LedgerStore(tmp_path / "e.jsonl")))
        reg = RegistryClient(client=self.registry, base_url="http://t")
        self.inner = reg
        self.kill = TestClient(create_kill_app(
            registry=wrap(reg) if wrap else reg,
            ledger=LedgerClient(client=self.ledger, base_url="http://t")))

    def register(self, agent_id, domain="finance"):
        assert self.registry.post("/agents", json={"agent_id": agent_id, "name": agent_id, "owner": "O",
                                                   "domain": domain}).status_code == 201

    def status(self, agent_id):
        return self.registry.get(f"/agents/{agent_id}").json()["status"]

    def events(self, event_type):
        return self.ledger.get("/events", params={"event_type": event_type}).json()


class Wrapped:
    """The kill-switch's registry: delegates everything; hooks are set per test."""

    def __init__(self, inner):
        self._inner = inner
        self.on_get = None            # called with (agent_id) before each get_agent; a non-None return replaces the answer
        self.on_set = None            # called with (agent_id, status) instead of the real write; its return is the answer
        self.after_set = None         # called with (agent_id, status) after a real write

    def get_agent(self, agent_id):
        if self.on_get is not None:
            out = self.on_get(agent_id)
            if out is not None:
                return out
        return self._inner.get_agent(agent_id)

    def list_agents(self, **kw):
        return self._inner.list_agents(**kw)

    def set_status(self, agent_id, status, **kw):
        if self.on_set is not None:
            return self.on_set(agent_id, status)
        out = self._inner.set_status(agent_id, status, **kw)
        if self.after_set is not None:
            self.after_set(agent_id, status)
        return out


def _stack(tmp_path):
    holder = {}

    def wrap(reg):
        holder["w"] = Wrapped(reg)
        return holder["w"]

    s = Stack(tmp_path, wrap)
    return s, holder["w"]


# --- drill restore race ----------------------------------------------------------------------------------------------


def test_R1_a_real_kill_after_the_drills_flip_is_not_undone_by_the_restore(tmp_path):
    s, w = _stack(tmp_path)
    s.register("a1")
    state = {"flipped": False, "fired": False}

    def after_set(agent_id, status):
        if status == "killed":
            state["flipped"] = True
    w.after_set = after_set

    def on_get(agent_id):
        if state["flipped"] and not state["fired"]:
            state["fired"] = True
            assert s.kill.post("/kill/a1", json=OP).status_code == 200     # the REAL kill, mid-drill
        return None
    w.on_get = on_get
    r = s.kill.post("/drill/a1", json=OP)
    assert state["fired"]
    assert s.status("a1") == "killed", "the drill's restore reversed a real kill"
    assert r.status_code >= 400
    [ev] = s.events("kill.drill.restore_skipped")
    assert "superseded" in ev["payload"]["reason"]


def test_R2_a_real_kill_between_the_drills_read_and_its_flip_is_not_undone(tmp_path):
    s, w = _stack(tmp_path)
    s.register("a1")
    state = {"fired": False}

    def on_get(agent_id):
        if state["fired"]:
            return None
        state["fired"] = True
        stale = dict(s.inner.get_agent(agent_id))                         # what the drill reads: status active
        assert s.kill.post("/kill/a1", json=OP).status_code == 200        # the real kill lands right after
        return stale
    w.on_get = on_get
    r = s.kill.post("/drill/a1", json=OP)
    assert s.status("a1") == "killed", "the drill restored a stale 'active' over a real kill"
    assert r.status_code >= 400
    assert len(s.events("kill.drill.restore_skipped")) == 1


def test_R3_a_real_kill_from_another_thread_during_a_drill_is_not_undone(tmp_path):
    s, w = _stack(tmp_path)
    s.register("a1")
    in_drill, killed = threading.Event(), threading.Event()
    state = {"flipped": False, "blocked": False}

    def after_set(agent_id, status):
        if status == "killed":
            state["flipped"] = True
    w.after_set = after_set

    def on_get(agent_id):
        if state["flipped"] and not state["blocked"]:
            state["blocked"] = True
            in_drill.set()
            assert killed.wait(20)
        return None
    w.on_get = on_get
    out = {}

    def real_kill():
        assert in_drill.wait(20)
        out["kill"] = s.kill.post("/kill/a1", json=OP).status_code
        killed.set()

    t = threading.Thread(target=real_kill)
    t.start()
    r = s.kill.post("/drill/a1", json=OP)
    t.join(30)
    assert out["kill"] == 200
    assert s.status("a1") == "killed"
    assert r.status_code >= 400


def test_an_undisturbed_drill_still_restores_and_answers_200(tmp_path):
    s = Stack(tmp_path)
    s.register("a1")
    r = s.kill.post("/drill/a1", json=OP)
    assert r.status_code == 200 and r.json()["restored"] is True
    assert s.status("a1") == "active" and s.events("kill.drill.restore_skipped") == []


def test_a_drill_does_not_unretire_an_agent_retired_while_it_ran(tmp_path):
    s, w = _stack(tmp_path)
    s.register("a1")
    state = {"flipped": False, "fired": False}
    w.after_set = lambda a, st: state.update(flipped=True) if st == "killed" else None

    def on_get(agent_id):
        if state["flipped"] and not state["fired"]:
            state["fired"] = True
            assert s.registry.patch("/agents/a1", json={"status": "retired"}).status_code == 200
        return None
    w.on_get = on_get
    s.kill.post("/drill/a1", json=OP)
    assert s.status("a1") == "retired"


# --- domain kill continues past a per-agent failure ----------------------------------------------------------------


def _domain_stack(tmp_path, behaviours):
    """Agents in domain finance; behaviours[agent] is an exception to raise on that agent's kill PATCH (None: fine)."""
    s, w = _stack(tmp_path)
    for a in behaviours:
        s.register(a)
    real = s.inner

    def on_set(agent_id, status):
        exc = behaviours.get(agent_id)
        if exc is not None and status == "killed":
            raise exc
        return real.set_status(agent_id, status)
    w.on_set = on_set
    return s


@pytest.mark.parametrize("exc", [
    AgentNotRegisteredError("a2"),                                              # a registry 404 on the PATCH
    RegistryUnreachableError("registry returned 500"),
    httpx.ReadTimeout("timed out"),                                             # a transport timeout, unwrapped
    ValueError("boom"),
], ids=["404", "500", "timeout", "unexpected"])
def test_a_failure_in_the_middle_of_a_domain_does_not_stop_the_later_agents(tmp_path, exc):
    s = _domain_stack(tmp_path, {"a1": None, "a2": exc, "a3": None, "a4": None})
    r = s.kill.post("/kill/domain/finance", json=OP)
    assert r.status_code >= 400, "a domain kill that left an agent running answered 2xx"
    assert {a: s.status(a) for a in ("a1", "a3", "a4")} == {"a1": "killed", "a3": "killed", "a4": "killed"}
    assert s.status("a2") == "active"
    report = r.json()["detail"]
    by = {x["agent_id"]: x["outcome"] for x in report["results"]}
    assert by == {"a1": "killed", "a2": "error", "a3": "killed", "a4": "killed"}
    [ev] = s.events("kill.domain")
    p = ev["payload"]
    assert [e["agent_id"] for e in p["errored"]] == ["a2"] and p["attempted"] == 4 and len(p["killed"]) == 3


def test_a_domain_with_a_404_then_a_500_then_a_timeout_attempts_every_agent(tmp_path):
    s = _domain_stack(tmp_path, {"a1": AgentNotRegisteredError("a1"),
                                 "a2": RegistryUnreachableError("registry returned 500"),
                                 "a3": httpx.ReadTimeout("t"), "a4": None, "a5": None})
    r = s.kill.post("/kill/domain/finance", json=OP)
    assert r.status_code >= 400
    assert s.status("a4") == "killed" and s.status("a5") == "killed"
    [ev] = s.events("kill.domain")
    assert sorted(e["agent_id"] for e in ev["payload"]["errored"]) == ["a1", "a2", "a3"]
    assert ev["payload"]["attempted"] == 5


def test_an_error_text_never_reaches_the_report_for_an_unexpected_exception(tmp_path):
    s = _domain_stack(tmp_path, {"a1": ValueError("SECRET-TOKEN-123"), "a2": None})
    r = s.kill.post("/kill/domain/finance", json=OP)
    assert "SECRET-TOKEN-123" not in r.text and "SECRET-TOKEN-123" not in str(s.events("kill.domain"))


def test_a_single_kill_whose_patch_is_a_registry_404_is_a_clean_4xx_not_a_500(tmp_path):
    s, w = _stack(tmp_path)
    s.register("a1")

    def boom(agent_id, status):
        raise AgentNotRegisteredError(agent_id)
    w.on_set = boom
    r = s.kill.post("/kill/a1", json=OP)
    assert r.status_code in (404, 502)


# --- a PATCH that does not say killed is not a kill ----------------------------------------------------------------


def test_a_patch_answering_200_with_status_active_is_not_reported_or_ledgered_as_a_kill(tmp_path):
    s, w = _stack(tmp_path)
    s.register("a1")
    w.on_set = lambda a, st: {"agent_id": a, "status": "active"}
    r = s.kill.post("/kill/a1", json=OP)
    assert r.status_code >= 400
    assert s.events("kill.agent") == []


@pytest.mark.parametrize("answer", [None, {}, {"status": "active"}, {"status": 1}, "killed"])
def test_a_domain_kill_counts_an_unconfirmed_patch_as_errored(tmp_path, answer):
    s, w = _stack(tmp_path)
    s.register("a1")
    s.register("a2")
    real = s.inner
    w.on_set = lambda a, st: answer if a == "a1" else real.set_status(a, st)
    r = s.kill.post("/kill/domain/finance", json=OP)
    assert r.status_code >= 400
    by = {x["agent_id"]: x["outcome"] for x in r.json()["detail"]["results"]}
    assert by["a1"] == "error" and by["a2"] == "killed"
    [ev] = s.events("kill.domain")
    assert ev["payload"]["killed"] == ["a2"]
