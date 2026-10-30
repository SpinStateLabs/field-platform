"""C-260 (reviewer C-248 follow-ups): a retired agent has no re-attestation (P1), an empty or name-only PATCH on a
retired agent still works (P2, kills the `and` -> `or` mutant of the frozen-field rule), and the README wording (P3).

`attest` is the only thing that moves `attested_at`, the field that clears lifecycle-manager's
`lifecycle.reattestation_due`. A decommissioned agent has no live lifecycle to re-attest; the refusal lives in the
store, in the same atomic step as the write (like the retired-is-terminal rule), and the API and CLI map it."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from agent_registry import cli
from agent_registry.api import create_app
from agent_registry.models import AgentStatus, AgentUpdate
from agent_registry.store import (AgentNotFoundError, RegistryStore, RetiredAgentError, RetiredAttestationError,
                                  RetiredRecordFrozenError)
from field_core import operator_auth as oa


@pytest.fixture(autouse=True)
def _flags_off(monkeypatch):
    for n in (oa.ENV_REGISTRY, oa.ENV_REQUIRE, oa.ENV_OPERATOR, oa.ENV_OPERATOR_KEY):
        monkeypatch.delenv(n, raising=False)


class Spy:
    def __init__(self):
        self.events = []

    def append(self, event_type, payload=None, agent_id=None):
        self.events.append((event_type, payload, agent_id))


@pytest.fixture()
def env(tmp_path):
    spy = Spy()
    store = RegistryStore(tmp_path / "a.sqlite3")
    c = TestClient(create_app(store=store, ledger=spy))
    assert c.post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O", "domain": "finance"}).status_code == 201
    spy.events.clear()
    return c, store, spy


def retire(c):
    assert c.patch("/agents/a1", json={"status": "retired"}).status_code == 200


# --- P1: attest on a retired agent ------------------------------------------------------------------------------


def test_the_api_refuses_to_attest_a_retired_agent_and_writes_nothing(env):
    c, store, spy = env
    retire(c)
    spy.events.clear()
    before = c.get("/agents/a1").json()
    r = c.post("/agents/a1/attest", json={"attested_by": "Don"})
    assert r.status_code == 409
    assert r.json()["detail"] == "agent 'a1' is retired - a retired agent has no re-attestation"
    assert c.get("/agents/a1").json() == before                      # attested_at, attested_by, updated_at untouched
    assert before["attested_at"] is None and before["attested_by"] is None
    assert [e for e in spy.events if e[0] == "registry.attested"] == []


def test_the_store_refuses_and_the_error_is_a_retired_agent_error(env):
    _, store, _ = env
    store.set_status("a1", AgentStatus.RETIRED)
    with pytest.raises(RetiredAttestationError):
        store.attest("a1", "Don")
    assert issubclass(RetiredAttestationError, RetiredAgentError)
    assert not issubclass(RetiredRecordFrozenError, RetiredAttestationError)
    rec = store.get("a1")
    assert rec.attested_at is None and rec.attested_by is None


def test_a_prior_attestation_on_a_since_retired_agent_is_kept_and_cannot_be_renewed(env):
    c, store, _ = env
    assert c.post("/agents/a1/attest", json={"attested_by": "Don"}).status_code == 200
    first = c.get("/agents/a1").json()
    retire(c)
    after_retire = c.get("/agents/a1").json()
    assert after_retire["attested_at"] == first["attested_at"] and after_retire["attested_by"] == "Don"
    assert c.post("/agents/a1/attest", json={"attested_by": "Someone Else"}).status_code == 409
    assert c.get("/agents/a1").json() == after_retire


@pytest.mark.parametrize("status", ["active", "killed"])
def test_a_live_or_killed_agent_can_still_be_attested(env, status):
    c, _, spy = env
    if status == "killed":
        assert c.patch("/agents/a1", json={"status": "killed"}).status_code == 200
    spy.events.clear()
    r = c.post("/agents/a1/attest", json={"attested_by": "Don"})
    assert r.status_code == 200 and r.json()["attested_by"] == "Don"
    assert [e[0] for e in spy.events if e[0] == "registry.attested"] == ["registry.attested"]


def test_an_unknown_agent_is_still_404_and_a_blank_attester_still_422(env):
    c, _, _ = env
    assert c.post("/agents/nobody/attest", json={"attested_by": "Don"}).status_code == 404
    assert c.post("/agents/a1/attest", json={"attested_by": "   "}).status_code == 422
    retire(c)
    assert c.post("/agents/a1/attest", json={"attested_by": "   "}).status_code == 422   # validated before the store
    assert c.post("/agents/nobody/attest", json={"attested_by": "Don"}).status_code == 404


def test_the_store_still_raises_not_found_for_an_unknown_agent(env):
    _, store, _ = env
    with pytest.raises(AgentNotFoundError):
        store.attest("nobody", "Don")


def test_the_store_attest_is_one_transaction_with_the_retired_check(env):
    """The check and the write share `BEGIN IMMEDIATE`: after a retirement commits, no attest can follow it."""
    _, store, _ = env
    store.attest("a1", "Don")
    store.set_status("a1", AgentStatus.RETIRED)
    for _ in range(3):
        with pytest.raises(RetiredAttestationError):
            store.attest("a1", "Don")
    assert store.get("a1").attested_by == "Don"


# --- the command ------------------------------------------------------------------------------------------------


def test_the_cli_exits_4_for_a_retired_agent_and_writes_nothing(tmp_path):
    db = tmp_path / "agents.sqlite3"
    store = RegistryStore(db)
    TestClient(create_app(store=store)).post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O"})
    store.set_status("a1", AgentStatus.RETIRED)
    store.close()
    r = CliRunner().invoke(cli.app, ["attest", "a1", "--by", "Don", "--path", str(db)])
    assert r.exit_code == 4, r.output
    assert "error: agent 'a1' is retired - a retired agent has no re-attestation" in r.output
    again = RegistryStore(db)
    assert again.get("a1").attested_at is None
    again.close()


def test_the_cli_exit_codes_for_the_other_cases_are_unchanged(tmp_path):
    db = tmp_path / "agents.sqlite3"
    store = RegistryStore(db)
    TestClient(create_app(store=store)).post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O"})
    store.close()
    run = lambda *a: CliRunner().invoke(cli.app, ["attest", *a, "--path", str(db)])
    assert run("nobody", "--by", "Don").exit_code == 1
    assert run("a1", "--by", "   ").exit_code == 2
    assert run("a1", "--by", "Don").exit_code in (0, 3)       # 0 attested; 3 only when a configured ledger refuses


# --- P2: an empty or name-only PATCH on a retired agent ------------------------------------------------------------


def test_an_empty_patch_on_a_retired_agent_is_accepted_and_changes_nothing(env):
    c, store, spy = env
    retire(c)
    spy.events.clear()
    before = c.get("/agents/a1").json()
    r = c.patch("/agents/a1", json={})
    assert r.status_code == 200 and r.json() == before            # updated_at included
    # pinned as found: an empty PATCH is ledgered like any update, with no field named and no status change
    assert spy.events == [("registry.updated", {"fields": []}, "a1")]


def test_the_store_update_with_nothing_to_change_on_a_retired_agent_returns_the_row_twice(env):
    _, store, _ = env
    store.set_status("a1", AgentStatus.RETIRED)
    before, after = store.update_with_previous("a1", AgentUpdate())
    assert before == after and before.status == AgentStatus.RETIRED


def test_a_name_only_patch_on_a_retired_agent_still_works_and_nothing_frozen_moves(env):
    c, _, _ = env
    retire(c)
    r = c.patch("/agents/a1", json={"name": "renamed"})
    assert r.status_code == 200 and r.json()["name"] == "renamed"
    assert (r.json()["owner"], r.json()["domain"], r.json()["status"]) == ("O", "finance", "retired")


def test_retiring_an_already_retired_agent_is_not_refused(env):
    c, _, _ = env
    retire(c)
    assert c.patch("/agents/a1", json={"status": "retired"}).status_code == 200


# --- P3: the README wording ---------------------------------------------------------------------------------------


README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")


def test_the_readme_no_longer_says_every_operator_mode_for_the_retired_rules():
    flat = " ".join(README.split())
    assert "returns 409 in every operator mode" not in flat
    assert flat.count("for any caller the operator guard lets through") >= 2
    assert "OFF mode lets every caller through" in flat


def test_the_readme_states_the_retired_attestation_rule_and_the_cli_exit():
    flat = " ".join(README.split())
    for phrase in ("A retired agent has no re-attestation", "returns 409", "`registry attest` exits 4",
                   "nothing written", "needs no operator identity under ENFORCE"):
        assert phrase in flat, phrase


# --- the check and the write are one atomic step against another connection ----------------------------------------


def test_a_retirement_committed_by_another_connection_just_before_the_write_is_not_attested_over(tmp_path):
    """A second connection takes the write lock and retires the agent. `attest` must wait for it (its own `BEGIN
    IMMEDIATE`) and then see `retired`; without the lock it reads the old `active` row first and writes the
    attestation over the decommission once the lock is released."""
    import sqlite3
    import threading
    import time

    db = tmp_path / "a.sqlite3"
    store = RegistryStore(db)
    TestClient(create_app(store=store)).post("/agents", json={"agent_id": "a1", "name": "a1", "owner": "O"})
    other = sqlite3.connect(db, timeout=10, isolation_level=None)
    other.execute("BEGIN IMMEDIATE")
    other.execute("UPDATE agents SET status='retired' WHERE agent_id='a1'")
    outcome: dict = {}

    def attest():
        try:
            outcome["record"] = store.attest("a1", "Don")
        except Exception as exc:       # noqa: BLE001 - the type is the assertion
            outcome["error"] = exc

    t = threading.Thread(target=attest)
    t.start()
    time.sleep(0.4)                    # attest is now waiting on the lock (or, without it, has read `active`)
    other.execute("COMMIT")
    t.join(timeout=15)
    other.close()
    assert isinstance(outcome.get("error"), RetiredAttestationError), outcome
    check = RegistryStore(db)
    assert check.get("a1").attested_at is None and check.get("a1").status == AgentStatus.RETIRED
    check.close()
    store.close()
