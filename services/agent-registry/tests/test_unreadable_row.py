"""S9-16: one stored row that cannot be read as an agent record is a NAMED failure, not an anonymous 500 everywhere.

The row is not hidden (a domain halt that skipped an unlisted agent would be worse than a refused read): get of that id
and list raise CorruptAgentRowError(agent_id, field) carrying the column NAME only; GET /agents and GET /agents/{id}
answer a fixed 500 text; /health says ok=False and agent_unreadable; every other agent still reads and PATCHes."""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.models import AgentCreate, AgentStatus, AgentUpdate
from agent_registry.store import AgentNotFoundError, CorruptAgentRowError, RegistryStore
from field_core import operator_auth as oa

MARK = "MARKER-0f3a-do-not-echo"


@pytest.fixture()
def store(tmp_path):
    s = RegistryStore(tmp_path / "agents.sqlite3")
    s.add(AgentCreate(agent_id="good", name="Good", owner="o", domain="finance"))
    s.add(AgentCreate(agent_id="bad", name="Bad", owner="o", domain="finance"))
    return s


def corrupt(store, column, value):
    with store._lock, store._conn:
        store._conn.execute(f"UPDATE agents SET {column} = ? WHERE agent_id = 'bad'", (value,))


BAD = [("status", "archived", "status"), ("status", MARK, "status"), ("created_at", "not-a-date", "created_at"),
       ("updated_at", MARK, "updated_at"), ("attested_at", MARK, "attested_at")]


@pytest.mark.parametrize("column,value,field", BAD)
def test_get_and_list_raise_the_named_error_with_the_field_name_only(store, column, value, field):
    corrupt(store, column, value)
    for call in (lambda: store.get("bad"), lambda: store.list()):
        with pytest.raises(CorruptAgentRowError) as exc:
            call()
        assert exc.value.agent_id == "bad" and exc.value.field == field
        assert str(exc.value) == f"agent record bad is unreadable ({field})"
        assert MARK not in str(exc.value) and exc.value.__cause__ is None and exc.value.__suppress_context__


def test_another_agent_still_reads_and_patches(store):
    corrupt(store, "status", "archived")
    assert store.get("good").name == "Good"
    assert store.update("good", AgentUpdate(name="Renamed")).name == "Renamed"
    assert store.update("good", AgentUpdate(status=AgentStatus.KILLED)).status == AgentStatus.KILLED


def test_a_missing_id_is_still_not_found_not_unreadable(store):
    corrupt(store, "status", "archived")
    with pytest.raises(AgentNotFoundError):
        store.get("absent")


def test_an_empty_attested_at_is_an_unattested_agent_not_a_corrupt_row(store):
    corrupt(store, "attested_at", "")
    assert store.get("bad").attested_at is None and len(store.list()) == 2


@pytest.mark.parametrize("column,value,field", BAD)
def test_the_routes_answer_a_fixed_500_and_health_reports_it(store, column, value, field):
    corrupt(store, column, value)
    c = TestClient(create_app(store=store), raise_server_exceptions=False)
    for path in ("/agents", "/agents/bad"):
        r = c.get(path)
        assert r.status_code == 500 and r.json() == {"detail": f"agent record bad is unreadable ({field})"}
        assert MARK not in r.text
    h = c.get("/health")
    assert h.status_code == 200 and h.json()["ok"] is False and h.json()["agent_unreadable"] is True
    assert h.json()["agent_count"] == 2 and MARK not in h.text
    assert c.get("/agents/good").status_code == 200
    assert c.patch("/agents/good", json={"name": "Renamed"}).status_code == 200


def test_a_good_database_is_unchanged(store):
    c = TestClient(create_app(store=store))
    h = c.get("/health").json()
    assert h["ok"] is True and h["agent_unreadable"] is False and h["agent_count"] == 2
    assert [a["agent_id"] for a in c.get("/agents").json()] == ["bad", "good"]


def test_the_stored_value_never_appears_in_the_error_or_the_log(store, caplog):
    corrupt(store, "created_at", MARK)
    c = TestClient(create_app(store=store), raise_server_exceptions=False)
    assert c.get("/agents/bad").status_code == 500
    assert MARK not in caplog.text


@pytest.mark.parametrize("column", ["created_at", "updated_at", "attested_at"])
def test_a_stored_value_of_the_wrong_type_is_the_same_named_error(store, column):
    """Bytes in a time column make the parser raise TypeError, not ValueError: still the named error."""
    corrupt(store, column, b"\x00\x01")
    for call in (lambda: store.get("bad"), lambda: store.list()):
        with pytest.raises(CorruptAgentRowError) as exc:
            call()
        assert exc.value.agent_id == "bad" and exc.value.field == column


def with_a_retired_agent(store):
    """good: a ref that resolves; bad: one that does not; gone: retired, with a ref that does not."""
    store.add(AgentCreate(agent_id="gone", name="Gone", owner="o", domain="finance",
                          manifest_ref="manifests/retired-absent.yaml"))
    store.update("gone", AgentUpdate(status=AgentStatus.RETIRED))
    for agent_id, ref in (("good", "manifests/invoicing-agent.yaml"), ("bad", "manifests/absent.yaml")):
        with store._lock, store._conn:
            store._conn.execute("UPDATE agents SET manifest_ref = ? WHERE agent_id = ?", (ref, agent_id))


def test_health_view_counts_every_row_and_lists_the_refs_of_rows_not_retired(store):
    with_a_retired_agent(store)
    corrupt(store, "status", "archived")
    count, refs = store.health_view()
    assert count == 3
    assert sorted(refs) == ["manifests/absent.yaml", "manifests/invoicing-agent.yaml"]


def test_unreadable_health_still_reports_unresolved_manifests_and_dropped_appends(store, tmp_path, monkeypatch):
    """Log-only operator mode, so that /health counts unresolved manifests."""
    monkeypatch.delenv(oa.ENV_REQUIRE, raising=False)
    monkeypatch.setenv(oa.ENV_REGISTRY, str(tmp_path / "operators.json"))
    (tmp_path / "operators.json").write_text("[]", encoding="utf-8")
    with_a_retired_agent(store)
    corrupt(store, "status", "archived")
    app = create_app(store=store)
    app.state.ledger_appends_dropped = 3
    h = TestClient(app, raise_server_exceptions=False).get("/health").json()
    assert h["ok"] is False and h["agent_unreadable"] is True and h["agent_count"] == 3
    assert h["operator_mode"] == "log-only"
    assert h["manifests_unresolved"] == 1
    assert h["ledger_appends_dropped"] == 3
