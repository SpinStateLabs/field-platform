"""B13: a PUT /contracts body that repeats a JSON key is refused (422), never read last-wins."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from federation_broker.api import create_app
from federation_broker.engine import BrokerEngine, ContractStore

JSON = {"content-type": "application/json"}


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(engine=BrokerEngine(store=ContractStore(tmp_path / "c.sqlite3"), ledger=None)))


def body_with(extra: str = "") -> str:
    """A valid contract body as raw text, with ``extra`` members appended verbatim (json.dumps cannot repeat keys)."""
    return ('{"contract_id": "C-1", "counterparty_org": "Acme Corp", '
            '"allowed_scopes": ["read"], "allowed_data_classes": ["meta"], "active": true' + extra + "}")


def put_raw(client, text: str):
    return client.put("/contracts/C-1", content=text.encode(), headers=JSON)


def test_a_body_without_repeats_is_stored(client):
    response = put_raw(client, body_with())
    assert response.status_code == 200, response.text
    assert client.get("/contracts").json()[0]["allowed_scopes"] == ["read"]


@pytest.mark.parametrize("extra, field", [
    (', "allowed_scopes": ["*"]', "allowed_scopes"),
    (', "allowed_data_classes": ["everything"]', "allowed_data_classes"),
    (', "active": false', "active"),
    (', "counterparty_org": "Other Org"', "counterparty_org"),
], ids=["scopes widened", "data classes widened", "active flipped", "org swapped"])
def test_a_repeated_key_is_refused_and_nothing_is_stored(client, extra, field):
    response = put_raw(client, body_with(extra))
    assert response.status_code == 422, response.text
    assert client.get("/contracts").json() == []      # neither the first value nor the last


def test_a_repeat_with_the_same_value_is_still_refused(client):
    assert put_raw(client, body_with(', "allowed_scopes": ["read"]')).status_code == 422


def test_the_last_wins_reading_never_reaches_an_existing_contract(client):
    assert put_raw(client, body_with()).status_code == 200
    assert put_raw(client, body_with(', "allowed_scopes": ["*"]')).status_code == 422
    assert client.get("/contracts").json()[0]["allowed_scopes"] == ["read"]


def test_the_refusal_does_not_quote_the_key_or_the_values(client):
    secret_name = "allowed_data_classes"
    response = put_raw(client, body_with(f', "{secret_name}": ["SYNTHETIC-VALUE-B13"]'))
    assert response.status_code == 422
    assert "SYNTHETIC-VALUE-B13" not in response.text
    assert secret_name not in response.text
    assert "repeats a JSON key" in response.json()["detail"]


def test_a_body_that_is_not_json_is_still_fastapis_own_422(client):
    response = put_raw(client, '{"contract_id": ')
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)    # the validation-error shape, not the B13 text


def test_an_ordinary_json_client_is_unaffected(client):
    body = json.loads(body_with())
    assert client.put("/contracts/C-1", json=body).status_code == 200


# ---- POST /crossing (triage-t12 N1 on #1300): the same refusal -----------------------------------------------------

def crossing_with(extra: str = "") -> str:
    return ('{"direction": "outbound", "counterparty_org": "Acme Corp", "agent_id": "a1", "manifest": {}, '
            '"scope": "read", "data_class": "meta"' + extra + "}")


def test_a_crossing_without_repeats_is_decided(client):
    response = client.post("/crossing", content=crossing_with().encode(), headers=JSON)
    assert response.status_code == 200, response.text
    assert response.json()["decision"] in {"ALLOW", "BLOCK", "ESCALATE"}


@pytest.mark.parametrize("extra", [
    ', "scope": "admin"',
    ', "counterparty_org": "Other Org"',
    ', "direction": "inbound"',
], ids=["scope swapped", "org swapped", "direction swapped"])
def test_a_crossing_that_repeats_a_key_is_refused_not_decided(client, extra):
    response = client.post("/crossing", content=crossing_with(extra).encode(), headers=JSON)
    assert response.status_code == 422, response.text
    assert "decision" not in response.text
    assert "admin" not in response.text and "Other Org" not in response.text


def test_a_repeat_inside_the_manifest_object_is_refused_too(client):
    text = crossing_with().replace('"manifest": {}', '"manifest": {"agent": {"name": "x", "name": "y"}}')
    response = client.post("/crossing", content=text.encode(), headers=JSON)
    assert response.status_code == 422
    assert "repeats a JSON key" in response.json()["detail"]
