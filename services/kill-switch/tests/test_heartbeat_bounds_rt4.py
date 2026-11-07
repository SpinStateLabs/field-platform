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


# ---- R-PR858-cd4a9e3 conditions: refusals leave a trace, the limit mismatch is pinned, counts and text are exact -----------

import logging  # noqa: E402


def test_a_malformed_id_is_counted_in_health_and_never_echoed_by_the_log(tmp_path, monkeypatch, caplog):
    """C2: a shadow agent with an upper-case id is neither recorded nor told to halt; it must not be invisible."""
    c, store = _client(tmp_path, monkeypatch)
    try:
        assert c.get("/health").json()["heartbeat_ids_refused"] == 0
        with caplog.at_level(logging.WARNING, logger=kill_api.log.name):
            for bad in ("MyBot-SECRETMARK", "%00x", "a" * (kill_api.MAX_HEARTBEAT_ID_LEN + 1)):
                assert c.post(f"/heartbeat/{bad}").status_code == 422
        assert c.get("/health").json()["heartbeat_ids_refused"] == 3
        assert store.all() == {}
        assert "SECRETMARK" not in caplog.text and "MyBot" not in caplog.text
        assert caplog.text.count("heartbeat check-in refused") == 1        # the first refusal is logged; not every one
        assert "heartbeats_refused" in c.get("/health").json() and c.get("/health").json()["heartbeats_refused"] == 0
    finally:
        store.close()


def test_the_malformed_id_log_line_repeats_every_hundredth_refusal(tmp_path, monkeypatch, caplog):
    c, store = _client(tmp_path, monkeypatch)
    try:
        with caplog.at_level(logging.WARNING, logger=kill_api.log.name):
            for _ in range(100):
                c.post("/heartbeat/BAD")
        assert caplog.text.count("heartbeat check-in refused") == 2           # the 1st and the 100th
    finally:
        store.close()


def test_a_valid_id_does_not_move_the_malformed_counter(tmp_path, monkeypatch):
    c, store = _client(tmp_path, monkeypatch)
    try:
        c.post("/heartbeat/ghost-1")
        c.post("/heartbeat/reg-1")
        assert c.get("/health").json()["heartbeat_ids_refused"] == 0
    finally:
        store.close()


def test_a_registered_agent_with_an_id_over_the_limit_cannot_check_in_the_pinned_mismatch(tmp_path, monkeypatch):
    """C3: the registry's agent-id rule has no maximum, this route does. Pinned so the registry change (a separate card)
    is a deliberate edit of this test."""
    c, store = _client(tmp_path, monkeypatch)
    try:
        long_registered = "reg-" + "a" * kill_api.MAX_HEARTBEAT_ID_LEN
        assert len(long_registered) > kill_api.MAX_HEARTBEAT_ID_LEN
        assert c.post(f"/heartbeat/{long_registered}").status_code == 422
        assert store.all() == {}
        assert c.post("/heartbeat/reg-" + "a" * (kill_api.MAX_HEARTBEAT_ID_LEN - 4)).status_code == 200   # exactly at the limit
    finally:
        store.close()


def test_registered_rows_do_not_count_toward_the_unregistered_cap(tmp_path, monkeypatch):
    """Mutant K9: counting every row would refuse the third ghost here."""
    c, store = _client(tmp_path, monkeypatch, cap=3)
    try:
        for i in range(5):
            assert c.post(f"/heartbeat/reg-{i}").status_code == 200
        for i in range(3):
            assert c.post(f"/heartbeat/ghost-{i}").status_code == 200
        assert c.post("/heartbeat/ghost-3").status_code == 429
    finally:
        store.close()


def test_the_429_text_is_fixed_and_never_carries_the_id(tmp_path, monkeypatch):
    """Mutant K19."""
    c, store = _client(tmp_path, monkeypatch, cap=1)
    try:
        c.post("/heartbeat/ghost-first")
        r = c.post("/heartbeat/ghost-refusedmark")
        assert r.status_code == 429
        assert r.json() == {"detail": "too many distinct unregistered agent ids have checked in"}
        assert "ghost-refusedmark" not in r.text
    finally:
        store.close()


def test_the_limits_are_the_documented_numbers():
    assert kill_api.MAX_HEARTBEAT_ID_LEN == 128 and kill_api.MAX_UNREGISTERED_HEARTBEATS == 500
