"""agent-registry's 422s never repeat a caller-chosen KEY NAME (C-1128; reviewer C-1123 F1, audit F-C1109-2).

The service's own handler dropped ``input`` and ``ctx`` but passed a body key through ``loc`` unless it looked like a
secret, so a made-up marker sent as a key came back on two routes. The field-core helper replaces any name that is not
a declared field. Every value here is a made-up marker."""
import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.store import RegistryStore

MARK = "MADE-UP-KEY-NAME-0123456789"


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(store=RegistryStore(tmp_path / "agents.sqlite3")))


@pytest.mark.parametrize("path", ["/agents", "/discover"])
def test_a_body_key_name_is_not_repeated_in_a_422(client, path):
    r = client.post(path, json={MARK: "x"})
    assert r.status_code == 422
    assert MARK not in r.text, r.text


@pytest.mark.parametrize("path,body", [("/agents", MARK), ("/discover", MARK), ("/agents", {"agent_id": [MARK]})])
def test_a_value_is_not_repeated_in_a_422(client, path, body):
    r = client.post(path, json=body)
    assert r.status_code == 422
    assert MARK not in r.text, r.text
