"""C-757 (Don's ruling on C-467, reviewer C-202 F-C202-3): a PUT /caps or POST /spend for an agent the registry
reports as retired still succeeds (the governor is a meter, not a gate), is logged once as a fixed line that names no
agent, and is counted on /health. A registry that cannot answer means no line and no refusal."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from field_core.clients import AgentNotRegisteredError, RegistryUnreachableError
from spend_governor import api as gov_api
from spend_governor.api import REGISTRY_STATUS_TTL, create_app
from spend_governor.core import GovernorStore

RETIRED = "retired-canary-9x"
ACTIVE = "active-canary-9x"
LOGGER = "spend_governor.api"


class FakeRegistry:
    def __init__(self, statuses=None, error=None):
        self.statuses = dict(statuses or {})
        self.error = error
        self.calls: list[str] = []

    def get_agent(self, agent_id):
        self.calls.append(agent_id)
        if self.error is not None:
            raise self.error
        if agent_id not in self.statuses:
            raise AgentNotRegisteredError(agent_id)
        return {"agent_id": agent_id, "status": self.statuses[agent_id]}


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


def make(tmp_path, registry, clock=None):
    app = create_app(store=GovernorStore(tmp_path / "s.sqlite3"), registry=registry, clock=clock)
    return TestClient(app)


def cap(agent_id):
    return {"agent_id": agent_id, "currency": "USD", "limit_cents": 50_000, "period": "daily",
            "escalate_at_pct": 80}


def settle(c):
    """The registry is asked off the request path (F-399-1): wait for the lookups the call queued."""
    assert c.app.state.wait_retired_lookups()


def put_cap(c, agent_id):
    r = c.put(f"/caps/{agent_id}", json=cap(agent_id))
    settle(c)
    return r


def spend(c, agent_id, cents=5):
    r = c.post("/spend", json={"agent_id": agent_id, "cents": cents})
    settle(c)
    return r


def lines(caplog):
    return [r for r in caplog.records if r.name == LOGGER and r.levelno == logging.WARNING
            and "retired" in r.getMessage()]


def test_a_retired_agents_spend_is_kept_logged_once_and_counted(tmp_path, caplog):
    clock = Clock()
    c = make(tmp_path, FakeRegistry({RETIRED: "retired"}), clock)
    assert put_cap(c, RETIRED).status_code == 200
    clock.now += gov_api.RETIRED_LOG_INTERVAL + timedelta(seconds=1)   # a new line is due for this agent
    caplog.clear()
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        r = spend(c, RETIRED)
    assert r.status_code == 201, r.text  # a meter, not a gate
    assert r.json()["spent_cents"] == 5   # the spend accumulated
    assert len(lines(caplog)) == 1
    assert c.get("/health").json()["retired_agent_metered"] >= 1


def test_a_retired_agents_cap_write_is_kept_logged_and_counted(tmp_path, caplog):
    c = make(tmp_path, FakeRegistry({RETIRED: "retired"}))
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        r = put_cap(c, RETIRED)
    assert r.status_code == 200
    assert len(lines(caplog)) == 1
    assert c.get("/health").json()["retired_agent_metered"] == 1
    assert c.get(f"/caps/{RETIRED}").status_code == 200  # the cap was stored


def test_an_active_agent_produces_no_line_and_no_count(tmp_path, caplog):
    c = make(tmp_path, FakeRegistry({ACTIVE: "active"}))
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        assert put_cap(c, ACTIVE).status_code == 200
        assert spend(c, ACTIVE).status_code == 201
    assert lines(caplog) == []
    assert c.get("/health").json()["retired_agent_metered"] == 0


def test_the_line_names_no_agent_and_no_caller_text(tmp_path, caplog):
    clock = Clock()
    c = make(tmp_path, FakeRegistry({RETIRED: "retired"}), clock)
    put_cap(c, RETIRED)
    clock.now += gov_api.RETIRED_LOG_INTERVAL + timedelta(seconds=1)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        c.post("/spend", json={"agent_id": RETIRED, "cents": 1, "note": "NOTE-CANARY-4411"})
        settle(c)
    text = " ".join(r.getMessage() + " " + str(r.args) for r in lines(caplog))
    assert lines(caplog)
    for canary in (RETIRED, RETIRED[:8], "NOTE-CANARY-4411"):
        assert canary not in text


@pytest.mark.parametrize("error", [RegistryUnreachableError("registry down"),
                                   AgentNotRegisteredError("x"), RuntimeError("boom")])
def test_a_registry_that_cannot_answer_means_no_line_and_no_refusal(tmp_path, caplog, error):
    c = make(tmp_path, FakeRegistry(error=error))
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        assert put_cap(c, RETIRED).status_code == 200
        assert spend(c, RETIRED).status_code == 201
    assert lines(caplog) == []
    assert c.get("/health").json()["retired_agent_metered"] == 0


def test_a_malformed_registry_answer_is_not_a_warning(tmp_path, caplog):
    class Odd:
        def get_agent(self, agent_id):
            return ["retired"]

    c = make(tmp_path, Odd())
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        assert put_cap(c, RETIRED).status_code == 200
    assert lines(caplog) == []


def test_without_a_registry_nothing_is_looked_up_and_nothing_changes(tmp_path, caplog):
    c = make(tmp_path, None)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        assert put_cap(c, RETIRED).status_code == 200
        assert spend(c, RETIRED).status_code == 201
    assert lines(caplog) == []
    assert c.get("/health").json()["retired_agent_metered"] == 0


def test_a_spend_for_an_agent_without_a_cap_is_still_refused_and_not_counted(tmp_path):
    c = make(tmp_path, FakeRegistry({RETIRED: "retired"}))
    assert spend(c, RETIRED).status_code == 404  # existing rule, unchanged
    assert c.get("/health").json()["retired_agent_metered"] == 0


def test_the_status_answer_is_cached_for_the_ttl_then_asked_again(tmp_path):
    reg = FakeRegistry({RETIRED: "retired"})
    clock = Clock()
    c = make(tmp_path, reg, clock)
    put_cap(c, RETIRED)
    spend(c, RETIRED)
    spend(c, RETIRED)
    assert reg.calls == [RETIRED]                       # one read serves the calls inside the TTL
    assert c.get("/health").json()["retired_agent_metered"] == 3  # every call is still counted
    clock.now += REGISTRY_STATUS_TTL + timedelta(seconds=1)
    reg.statuses[RETIRED] = "active"                    # re-activated: the next read sees it
    spend(c, RETIRED)
    assert reg.calls == [RETIRED, RETIRED]
    assert c.get("/health").json()["retired_agent_metered"] == 3


def test_the_cache_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(gov_api, "REGISTRY_STATUS_CACHE_MAX", 3)
    reg = FakeRegistry({f"a{i}": "active" for i in range(10)})
    c = make(tmp_path, reg)
    for i in range(10):
        put_cap(c, f"a{i}")
    put_cap(c, "a0")  # the oldest entry was dropped, so it is read again
    assert reg.calls.count("a0") == 2
    assert len(reg.calls) == 11


# --- F-399-1 (reviewer C-1058): the lookup never runs on the request path and is bounded. The assertions are on
# call counts and on what happens while the registry is blocked, never on wall-clock time.

import threading


class BlockingRegistry:
    """get_agent waits on a gate; records the calling thread, the calls and the most that ran at once."""

    def __init__(self, status="retired"):
        self.gate = threading.Event()
        self.status = status
        self.calls: list[str] = []
        self.threads: set[str] = set()
        self.running = 0
        self.max_running = 0
        self._lock = threading.Lock()

    def get_agent(self, agent_id):
        with self._lock:
            self.calls.append(agent_id)
            self.threads.add(threading.current_thread().name)
            self.running += 1
            self.max_running = max(self.max_running, self.running)
        try:
            assert self.gate.wait(10)
            return {"agent_id": agent_id, "status": self.status}
        finally:
            with self._lock:
                self.running -= 1


def raw_put_cap(c, agent_id):
    return c.put(f"/caps/{agent_id}", json=cap(agent_id))


def raw_spend(c, agent_id):
    return c.post("/spend", json={"agent_id": agent_id, "cents": 1})


def test_a_blocked_registry_does_not_hold_up_any_spend_and_one_read_serves_every_waiting_call(tmp_path):
    reg = BlockingRegistry()
    c = make(tmp_path, reg)
    assert raw_put_cap(c, RETIRED).status_code == 200      # returns while the registry is still blocked
    for _ in range(40):                                    # every spend returns with the gate shut
        assert raw_spend(c, RETIRED).status_code == 201
    assert reg.gate.is_set() is False
    reg.gate.set()
    settle(c)
    assert reg.calls == [RETIRED]                          # one read, joined by all 41 calls
    assert c.get("/health").json()["retired_agent_metered"] == 41   # none lost
    assert not any(t.startswith("anyio") or t == "MainThread" for t in reg.threads)
    assert all(t.startswith("registry-status") for t in reg.threads)  # never the shared sync pool


def test_lookups_are_bounded_in_parallelism_and_in_pending_agents(tmp_path, monkeypatch):
    monkeypatch.setattr(gov_api, "REGISTRY_LOOKUP_MAX_PENDING", 3)
    reg = BlockingRegistry(status="active")
    c = make(tmp_path, reg)
    for i in range(8):                                     # 8 distinct agents, registry blocked
        assert raw_put_cap(c, f"b{i}").status_code == 200
    reg.gate.set()
    settle(c)
    assert len(reg.calls) == 3                             # only 3 agents were ever queued; 5 were not looked up
    assert reg.max_running <= gov_api.REGISTRY_LOOKUP_WORKERS


def test_a_failure_to_answer_is_remembered_briefly_then_asked_again(tmp_path):
    reg = FakeRegistry(error=RegistryUnreachableError("down"))
    clock = Clock()
    c = make(tmp_path, reg, clock)
    put_cap(c, "unknown-1")
    for _ in range(50):
        spend(c, "unknown-1")
    assert reg.calls == ["unknown-1"]                      # 51 calls, one read: the failure is cached
    clock.now += gov_api.REGISTRY_FAILURE_TTL + timedelta(seconds=1)
    spend(c, "unknown-1")
    assert reg.calls == ["unknown-1", "unknown-1"]         # asked again after the short failure TTL
    assert gov_api.REGISTRY_FAILURE_TTL < REGISTRY_STATUS_TTL


# --- F-399-2 (reviewer C-1058): "logged once" is once per agent per RETIRED_LOG_INTERVAL, every call still counted.

def test_a_retired_agent_is_logged_once_per_interval_not_once_per_call(tmp_path, caplog):
    clock = Clock()
    c = make(tmp_path, FakeRegistry({RETIRED: "retired"}), clock)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        put_cap(c, RETIRED)
        for _ in range(25):
            assert spend(c, RETIRED).status_code == 201
        assert len(lines(caplog)) == 1                                   # 26 calls, one line
        assert c.get("/health").json()["retired_agent_metered"] == 26    # all counted
        clock.now += gov_api.RETIRED_LOG_INTERVAL + timedelta(seconds=1)
        spend(c, RETIRED)
    assert len(lines(caplog)) == 2
    assert "25 more since" in lines(caplog)[1].getMessage()              # the second line stands for the 25 held back
    assert c.get("/health").json()["retired_agent_metered"] == 27


def test_the_interval_is_per_agent(tmp_path, caplog):
    c = make(tmp_path, FakeRegistry({RETIRED: "retired", "other-retired-canary": "retired"}))
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        put_cap(c, RETIRED)
        put_cap(c, "other-retired-canary")
    assert len(lines(caplog)) == 2
