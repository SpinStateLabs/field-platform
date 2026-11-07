"""B-RT4 F1: POST /heartbeat/{agent_id} bounds what it stores.

Reviewer R-RT-HARD-4 F1: any perimeter-secret holder could post unbounded
distinct ids (300 rows in the probe), an id of 50000 characters, and a NUL
id, each answered 200 and stored. The route has no operator guard on purpose
(a check-in is the agent's own self-report; an agent holds no operator key),
so the fix bounds the id and the number of unregistered rows instead.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import kill_switch.api as kill_api
from kill_switch.store import HeartbeatStore


class _Registry:
    """``reg-*`` ids are registered and active; everything else is unknown."""

    def get_agent(self, agent_id: str) -> dict:
        if agent_id.startswith("reg-"):
            return {"agent_id": agent_id, "status": "active", "domain": "d",
                    "name": agent_id, "owner": "o"}
        raise kill_api.AgentNotRegisteredError(agent_id)

    def list_agents(self, status=None) -> list:
        return []                                                       # /liveness lists the registered agents: none needed here


class _Ledger:
    def append(self, *args, **kwargs) -> None:
        return None


def _client(tmp_path, monkeypatch, cap=5):
    monkeypatch.setattr(kill_api, "MAX_UNREGISTERED_HEARTBEATS", cap)
    store = HeartbeatStore(tmp_path / "hb.sqlite3")
    app = kill_api.create_app(registry=_Registry(), ledger=_Ledger(), heartbeats=store)
    return TestClient(app), store


def test_oversized_id_refused_and_not_stored(tmp_path, monkeypatch):
    c, store = _client(tmp_path, monkeypatch)
    try:
        r = c.post("/heartbeat/" + "a" * (kill_api.MAX_HEARTBEAT_ID_LEN + 1))
        assert r.status_code == 422
        assert store.all() == {}
        ok = c.post("/heartbeat/" + "a" * kill_api.MAX_HEARTBEAT_ID_LEN)
        assert ok.status_code == 200
        assert len(store.all()) == 1
    finally:
        store.close()


def test_malformed_ids_refused(tmp_path, monkeypatch):
    c, store = _client(tmp_path, monkeypatch)
    try:
        for bad in ("%00x", "UPPER", "-lead", "has%20space", "a%5Cb", ".x"):
            assert c.post(f"/heartbeat/{bad}").status_code == 422, bad
        assert store.all() == {}
    finally:
        store.close()


def test_unregistered_rows_are_capped(tmp_path, monkeypatch):
    c, store = _client(tmp_path, monkeypatch, cap=5)
    try:
        for i in range(5):
            assert c.post(f"/heartbeat/ghost-{i}").status_code == 200
        r = c.post("/heartbeat/ghost-5")
        assert r.status_code == 429
        assert len(store.all()) == 5
        assert "ghost-5" not in store.all()
    finally:
        store.close()


def test_known_unregistered_and_registered_ids_still_check_in_at_cap(tmp_path, monkeypatch):
    c, store = _client(tmp_path, monkeypatch, cap=2)
    try:
        for i in range(2):
            c.post(f"/heartbeat/ghost-{i}")
        # an id already stored keeps updating (checkins increments)
        assert c.post("/heartbeat/ghost-0").status_code == 200
        assert store.get("ghost-0")["checkins"] == 2
        # a registered agent is never refused by the unregistered cap
        r = c.post("/heartbeat/reg-1")
        assert r.status_code == 200 and r.json()["killed"] is False
        assert store.get("reg-1")["status"] == "active"
    finally:
        store.close()


def test_refused_checkin_still_does_not_write_on_get(tmp_path, monkeypatch):
    c, store = _client(tmp_path, monkeypatch, cap=1)
    try:
        c.post("/heartbeat/ghost-0")
        g = c.get("/heartbeat/ghost-9")
        assert g.status_code == 200 and g.json()["killed"] is True
        assert "ghost-9" not in store.all()
    finally:
        store.close()


# ---- review C1 (ssl-ff-reviewer-10): a full table must not be a silent blind spot --------------------------------------

def test_refused_check_ins_are_counted_in_health_and_liveness(tmp_path, monkeypatch):
    c, store = _client(tmp_path, monkeypatch, cap=3)
    try:
        for i in range(3):
            assert c.post(f"/heartbeat/ghost-{i}").status_code == 200
        assert c.get("/health").json()["heartbeats_refused"] == 0
        for i in range(3, 8):
            assert c.post(f"/heartbeat/ghost-{i}").status_code == 429
        assert c.get("/health").json()["heartbeats_refused"] == 5
        live = c.get("/liveness").json()
        assert live["unregistered_check_ins_refused"] == 5 and live["unregistered_check_in_cap"] == 3
    finally:
        store.close()


def test_only_refusals_for_a_full_table_are_counted(tmp_path, monkeypatch):
    """Not an invalid id (422), not an id already stored, not a registered agent: none of these is a lost shadow agent."""
    c, store = _client(tmp_path, monkeypatch, cap=2)
    try:
        for i in range(2):
            c.post(f"/heartbeat/ghost-{i}")
        assert c.post("/heartbeat/ghost-0").status_code == 200            # already stored: recorded again
        assert c.post("/heartbeat/reg-agent").status_code == 200          # registered: always recorded
        assert c.post("/heartbeat/UPPER").status_code == 422              # invalid id
        assert c.get("/health").json()["heartbeats_refused"] == 0
        assert c.post("/heartbeat/ghost-new").status_code == 429
        assert c.get("/health").json()["heartbeats_refused"] == 1
    finally:
        store.close()


def test_the_first_refusal_and_every_hundredth_are_logged_without_the_refused_id(tmp_path, monkeypatch, caplog):
    import logging

    c, store = _client(tmp_path, monkeypatch, cap=1)
    try:
        c.post("/heartbeat/ghost-0")
        with caplog.at_level(logging.WARNING, logger="kill_switch.api"):
            for i in range(1, 202):
                c.post(f"/heartbeat/secret-marker-{i}")
        lines = [r.getMessage() for r in caplog.records if "heartbeat table full" in r.getMessage()]
        assert len(lines) == 3                                             # refusals 1, 100 and 200 of 201
        assert lines[0].startswith("heartbeat table full: 1 new unregistered") and "200 new" in lines[2]
        assert not any("secret-marker" in m for m in lines)
    finally:
        store.close()
