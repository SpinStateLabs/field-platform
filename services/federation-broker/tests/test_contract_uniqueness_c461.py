"""C-461 (reviewer C-355 F-C355-2/-3): one active contract per counterparty org, a deterministic `for_org`, and the
keyless guard decided before the scope check.

A keyless contract registered next to a keyed one for the same org used to be accepted (200), and which row decided
an inbound crossing was whatever SQLite returned. Now the second ACTIVE contract is refused with 409; the same id
re-registers (replaces), an inactive one is fine, and an org's contract is changed to a new id by deactivating the
old one first. A database written before the rule resolves to the lowest contract_id every time."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from federation_broker.api import create_app
from federation_broker.engine import (
    BrokerEngine, ContractConflict, ContractStore, FederationContract, normalise_org)
from field_core.signing import generate_keypair
from test_federation_broker import COUNTERPARTY, counterparty_manifest

OTHER_ORG = "Other Example Corp"


@pytest.fixture()
def stack(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_ORG_NAME", "Spin State Labs")
    store = ContractStore(tmp_path / "contracts.sqlite3")
    return TestClient(create_app(engine=BrokerEngine(store=store))), store


def body(contract_id, org=COUNTERPARTY, key=None, active=True):
    return {"contract_id": contract_id, "counterparty_org": org, "allowed_scopes": ["exchange invoice status"],
            "allowed_data_classes": ["invoice metadata"], "counterparty_pubkey_pem": key, "active": active}


def put(client, contract_id, **kw):
    return client.put(f"/contracts/{contract_id}", json=body(contract_id, **kw))


def ids(client):
    return sorted(c["contract_id"] for c in client.get("/contracts").json())


def test_a_keyless_contract_beside_a_keyed_one_for_the_same_org_is_refused(stack):
    client, _ = stack
    _, public_pem = generate_keypair()
    assert put(client, "FED-2026-001", key=public_pem).status_code == 200
    r = put(client, "FED-2026-002")                       # the report's probe: keyless FED-2026-002 next to keyed 001
    assert r.status_code == 409, r.text
    assert "FED-2026-001" in r.text and "one active contract per org" in r.text
    assert ids(client) == ["FED-2026-001"]                # nothing was stored


def test_two_keyed_active_contracts_for_one_org_are_refused_too(stack):
    client, _ = stack
    _, k1 = generate_keypair()
    _, k2 = generate_keypair()
    assert put(client, "FED-A", key=k1).status_code == 200
    assert put(client, "FED-B", key=k2).status_code == 409


def test_the_same_contract_id_re_registers_and_replaces(stack):
    client, _ = stack
    _, public_pem = generate_keypair()
    assert put(client, "FED-2026-001", key=public_pem).status_code == 200
    assert put(client, "FED-2026-001").status_code == 200                   # keyless now: replaced, not refused
    only = client.get("/contracts").json()
    assert [c["contract_id"] for c in only] == ["FED-2026-001"] and not only[0]["counterparty_pubkey_pem"]


def test_an_inactive_second_contract_is_accepted_but_cannot_be_activated_beside_an_active_one(stack):
    client, _ = stack
    assert put(client, "FED-A").status_code == 200
    assert put(client, "FED-B", active=False).status_code == 200
    assert ids(client) == ["FED-A", "FED-B"]
    assert put(client, "FED-B", active=True).status_code == 409           # activating it beside FED-A
    assert put(client, "FED-A", active=False).status_code == 200          # deactivate the old one first ...
    assert put(client, "FED-B", active=True).status_code == 200           # ... then the new id may be active


def test_changing_an_orgs_contract_to_a_new_id_goes_through_deactivation(stack):
    client, store = stack
    assert put(client, "FED-OLD").status_code == 200
    assert put(client, "FED-OLD", active=False).status_code == 200
    assert put(client, "FED-NEW").status_code == 200
    assert store.for_org(COUNTERPARTY).contract_id == "FED-NEW"


def test_another_orgs_contract_is_not_affected(stack):
    client, store = stack
    assert put(client, "FED-A").status_code == 200
    assert put(client, "FED-X", org=OTHER_ORG).status_code == 200
    assert store.for_org(COUNTERPARTY).contract_id == "FED-A" and store.for_org(OTHER_ORG).contract_id == "FED-X"


def test_the_store_itself_refuses_the_second_active_contract(stack):
    _, store = stack
    base = dict(counterparty_org=COUNTERPARTY, allowed_scopes=["s"], allowed_data_classes=["d"])
    store.save(FederationContract(contract_id="FED-A", **base))
    with pytest.raises(ContractConflict, match="FED-A"):
        store.save(FederationContract(contract_id="FED-B", **base))
    assert [c.contract_id for c in store.list()] == ["FED-A"]


def _legacy_row(store, contract_id, org=COUNTERPARTY, key=None):
    """A row written the way a database from before the one-active rule holds it: straight into the table."""
    with store._lock, store._conn:
        store._conn.execute("DROP INDEX IF EXISTS contracts_one_active_org")    # C-483: a database that holds duplicates has none
        store._conn.execute(
            "INSERT INTO contracts (contract_id, counterparty_org, allowed_scopes, allowed_data_classes, contract_ref, "
            "pubkey, active, org_key) VALUES (?,?,?,?,?,?,1,?)",
            (contract_id, org, json.dumps(["exchange invoice status"]), json.dumps(["invoice metadata"]), None, key,
             normalise_org(org)))


def test_a_legacy_database_with_two_active_rows_resolves_to_the_lowest_contract_id_every_time(stack):
    _, store = stack
    _legacy_row(store, "FED-B")           # inserted FIRST: insertion order would pick it
    _legacy_row(store, "FED-A")
    for _ in range(3):
        assert store.for_org(COUNTERPARTY).contract_id == "FED-A"


def test_a_legacy_keyless_row_that_sorts_first_blocks_inbound_rather_than_letting_the_keyed_one_decide(stack):
    client, store = stack
    _, public_pem = generate_keypair()
    _legacy_row(store, "FED-A-keyless")
    _legacy_row(store, "FED-B-keyed", key=public_pem)
    r = client.post("/crossing", json={
        "counterparty_org": COUNTERPARTY, "counterparty_agent_id": "borealis-billing-agent",
        "counterparty_manifest": counterparty_manifest(), "scope": "exchange invoice status",
        "data_class": "invoice metadata"}).json()
    assert r["decision"] == "BLOCK" and "FED-A-keyless" in r["reasons"][0]


def test_the_keyless_guard_decides_before_the_scope_check(stack):
    """F-C355-3: a keyless contract with an out-of-scope request says WHY the contract is refused (no key), not that
    the scope is wrong: the guard sits before `_outside_contract`."""
    client, _ = stack
    assert put(client, "FED-2026-001").status_code == 200
    for scope, data_class in (("pull full customer ledger", "invoice metadata"),
                              ("exchange invoice status", "customer PII"),
                              ("pull full customer ledger", "customer PII")):
        r = client.post("/crossing", json={
            "counterparty_org": COUNTERPARTY, "counterparty_agent_id": "borealis-billing-agent",
            "counterparty_manifest": counterparty_manifest(), "scope": scope, "data_class": data_class}).json()
        assert r["decision"] == "BLOCK" and r["clause_id"] == "F.peer", r
        assert "inbound crossings require a contract key" in r["reasons"][0], r["reasons"]
        assert "not in contract" not in r["reasons"][0]
