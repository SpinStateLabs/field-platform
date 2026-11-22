"""B12: a row stored before the NAME_MAX cap existed still lists; writes keep the cap.

``GET /contracts`` used to validate every stored row against the WRITE model, so one legacy row with a name over
256 characters made the listing answer 500 for every lister. Reads now use ``StoredFederationContract`` (no length
caps); ``PUT /contracts`` still refuses a 257-character name with 422.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from federation_broker.api import create_app
from federation_broker.engine import (
    NAME_MAX,
    BrokerEngine,
    ContractStore,
    FederationContract,
    StoredFederationContract,
)

LONG = "L" * (NAME_MAX + 44)


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(engine=BrokerEngine(store=ContractStore(tmp_path / "c.sqlite3"), ledger=None)))


def contract_body(**over):
    body = {"contract_id": "C-1", "counterparty_org": "Acme Corp",
            "allowed_scopes": ["read"], "allowed_data_classes": ["meta"], "active": True}
    body.update(over)
    return body


def legacy_row(client, **over):
    """Store a row the write model would refuse: ``model_construct`` skips validation, as a pre-cap write did."""
    client.app.state.engine.store.save(FederationContract.model_construct(**contract_body(contract_ref=None, **over)))


@pytest.mark.parametrize("field, value", [
    ("contract_id", LONG),
    ("counterparty_org", LONG),
    ("allowed_scopes", [LONG]),
    ("allowed_data_classes", [LONG]),
    ("contract_ref", LONG),
], ids=["contract_id", "counterparty_org", "a scope", "a data class", "contract_ref"])
def test_a_legacy_row_with_a_long_name_lists_in_full(client, field, value):
    legacy_row(client, **{field: value})
    listed = client.get("/contracts")
    assert listed.status_code == 200, listed.status_code
    [row] = listed.json()
    assert row[field] == value          # served whole: not truncated, not dropped


def test_one_legacy_row_does_not_hide_the_others(client):
    assert client.put("/contracts/C-0", json=contract_body(contract_id="C-0", counterparty_org="Beta Org")).status_code == 200
    legacy_row(client, contract_id="C-1", counterparty_org=LONG)
    listed = client.get("/contracts")
    assert listed.status_code == 200
    assert [r["contract_id"] for r in listed.json()] == ["C-0", "C-1"]


@pytest.mark.parametrize("field, value", [
    ("counterparty_org", LONG),
    ("allowed_scopes", [LONG]),
    ("allowed_data_classes", [LONG]),
    ("contract_ref", LONG),
], ids=["counterparty_org", "a scope", "a data class", "contract_ref"])
def test_writes_keep_the_cap(client, field, value):
    response = client.put("/contracts/C-1", json=contract_body(**{field: value}))
    assert response.status_code == 422
    assert client.get("/contracts").json() == []


def test_a_write_at_the_cap_is_still_accepted(client):
    at_cap = "A" * NAME_MAX
    assert client.put("/contracts/C-1", json=contract_body(counterparty_org=at_cap)).status_code == 200
    assert client.get("/contracts").json()[0]["counterparty_org"] == at_cap


def test_the_write_model_still_refuses_a_long_name_outside_the_api():
    with pytest.raises(ValueError):
        FederationContract(**contract_body(counterparty_org=LONG))


def test_the_stored_row_model_keeps_every_other_check():
    """Only the length caps are lifted: a blank name and an empty scope list are still refused on read."""
    with pytest.raises(ValueError, match="blank"):
        StoredFederationContract(**contract_body(counterparty_org="   "))
    with pytest.raises(ValueError):
        StoredFederationContract(**contract_body(allowed_scopes=[]))
    with pytest.raises(ValueError):
        StoredFederationContract(**contract_body(contract_id=""))
