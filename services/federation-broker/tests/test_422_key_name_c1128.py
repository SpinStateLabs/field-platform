"""federation-broker's 422s never repeat a caller-chosen KEY NAME (C-1128; reviewer C-1123 F1, audit F-C1109-2).

The service's own handler dropped ``input`` only, so a body key sent as a made-up marker came back on POST /crossing.
The field-core helper replaces any name that is not a declared field. Every value here is a made-up marker."""
import pytest
from fastapi.testclient import TestClient

from federation_broker.api import create_app
from federation_broker.engine import BrokerEngine, ContractStore

MARK = "MADE-UP-KEY-NAME-0123456789"


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(engine=BrokerEngine(store=ContractStore(tmp_path / "contracts.sqlite3"))))


def test_a_body_key_name_is_not_repeated_in_a_422(client):
    r = client.post("/crossing", json={MARK: "x"})
    assert r.status_code == 422
    assert MARK not in r.text, r.text


@pytest.mark.parametrize("body", [MARK, {"contract_id": [MARK]}])
def test_a_value_is_not_repeated_in_a_422(client, body):
    r = client.post("/crossing", json=body)
    assert r.status_code == 422
    assert MARK not in r.text, r.text
