"""S4-14: free-text fields of contracts and crossings are bounded; whitespace-only names refused; 422 never echoes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from federation_broker.api import create_app
from federation_broker.engine import BrokerEngine, ContractStore, FederationContract

NAME_MAX = 256
LIST_MAX = 100


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(engine=BrokerEngine(store=ContractStore(tmp_path / "c.sqlite3"), ledger=None)))


def contract_body(**over):
    body = {"contract_id": "C-1", "counterparty_org": "Acme Corp",
            "allowed_scopes": ["read"], "allowed_data_classes": ["meta"], "active": True}
    body.update(over)
    return body


def put(client, **over):
    body = contract_body(**over)
    return client.put(f"/contracts/{body['contract_id']}", json=body)


def crossing(client, **over):
    body = {"direction": "outbound", "counterparty_org": "Acme Corp", "agent_id": "a1",
            "manifest": {}, "scope": "read", "data_class": "meta"}
    body.update(over)
    return client.post("/crossing", json=body)


# ---- contracts ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["counterparty_org", "contract_ref"])
def test_contract_text_at_limit_ok_over_limit_422(client, field):
    ok = put(client, **{field: "x" * NAME_MAX})
    assert ok.status_code == 200, ok.text
    over = put(client, contract_id="C-2", **{field: "y" * (NAME_MAX + 1)})
    assert over.status_code == 422
    assert "y" * 20 not in over.text


def test_contract_id_over_limit_422(client):
    assert put(client, contract_id="i" * (NAME_MAX + 1)).status_code == 422


def test_contract_scope_item_over_limit_422(client):
    assert put(client, allowed_scopes=["s" * (NAME_MAX + 1)]).status_code == 422
    assert put(client, allowed_data_classes=["d" * (NAME_MAX + 1)]).status_code == 422


def test_contract_list_size_cap(client):
    assert put(client, allowed_scopes=[f"s{i}" for i in range(LIST_MAX)]).status_code == 200
    assert put(client, allowed_scopes=[f"s{i}" for i in range(LIST_MAX + 1)]).status_code == 422
    assert put(client, allowed_data_classes=[f"d{i}" for i in range(LIST_MAX + 1)]).status_code == 422


@pytest.mark.parametrize("field,val", [
    ("counterparty_org", "   "), ("allowed_scopes", ["  "]), ("allowed_data_classes", ["\t"]),
])
def test_contract_whitespace_only_refused(client, field, val):
    assert put(client, **{field: val}).status_code == 422


# ---- crossings ------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("field", ["counterparty_org", "scope", "data_class", "request_summary", "agent_id"])
def test_crossing_text_over_limit_422_no_echo(client, field):
    r = crossing(client, **{field: "z" * (NAME_MAX + 1)})
    assert r.status_code == 422
    assert "z" * 20 not in r.text


def test_crossing_inbound_names_over_limit_422(client):
    base = dict(direction="inbound", counterparty_manifest={}, counterparty_agent_id="p1")
    base.pop("counterparty_agent_id")
    r = crossing(client, agent_id=None, manifest=None, counterparty_manifest={},
                 counterparty_agent_id="p" * (NAME_MAX + 1), direction="inbound")
    assert r.status_code == 422
    r = crossing(client, agent_id=None, manifest=None, counterparty_manifest={}, counterparty_agent_id="p1",
                 direction="inbound", manifest_signature="s" * (513))
    assert r.status_code == 422


@pytest.mark.parametrize("field", ["scope", "data_class", "counterparty_org"])
def test_crossing_whitespace_only_422(client, field):
    assert crossing(client, **{field: "   "}).status_code == 422


def test_crossing_at_limit_is_decided_not_422(client):
    r = crossing(client, scope="s" * NAME_MAX, data_class="d" * NAME_MAX, request_summary="r" * NAME_MAX)
    assert r.status_code == 200


def test_normal_crossing_unchanged(client):
    assert crossing(client).status_code == 200


def test_model_level_bounds():
    with pytest.raises(ValueError):
        FederationContract(**contract_body(counterparty_org="o" * (NAME_MAX + 1)))
