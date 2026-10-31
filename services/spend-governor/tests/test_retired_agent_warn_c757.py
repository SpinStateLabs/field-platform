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


def put_cap(c, agent_id):
    return c.put(f"/caps/{agent_id}", json=cap(agent_id))


def spend(c, agent_id, cents=5):
    return c.post("/spend", json={"agent_id": agent_id, "cents": cents})


def lines(caplog):
    return [r for r in caplog.records if r.name == LOGGER and r.levelno == logging.WARNING
            and "retired" in r.getMessage()]


def test_a_retired_agents_spend_is_kept_logged_once_and_counted(tmp_path, caplog):
    c = make(tmp_path, FakeRegistry({RETIRED: "retired"}))
    assert put_cap(c, RETIRED).status_code == 200
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
    c = make(tmp_path, FakeRegistry({RETIRED: "retired"}))
    put_cap(c, RETIRED)
    with caplog.at_level(logging.WARNING, logger=LOGGER):
        c.post("/spend", json={"agent_id": RETIRED, "cents": 1, "note": "NOTE-CANARY-4411"})
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
