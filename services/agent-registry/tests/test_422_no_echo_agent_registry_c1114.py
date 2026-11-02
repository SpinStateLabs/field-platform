"""agent-registry's 422s never repeat the caller's text (C-1128; reviewer C-1123 F1, C-1109 F-C1109-2).

The service kept its own 422 handler, which redacts credential-shaped text but not a plain field NAME the caller sent: an
object body whose key is the marker came back in `loc` on POST /agents and POST /discover. The field-core handler
(C-1018) replaces such a name. Every value here is a made-up marker, not credential-shaped."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agent_registry.api import create_app
from agent_registry.store import RegistryStore

MARK = "MADE-UP-MARKER-0123456789"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    store = RegistryStore(tmp_path / "agents.sqlite3")
    yield TestClient(create_app(store=store), raise_server_exceptions=False)
    store.close()


@pytest.mark.parametrize("path", ["/agents", "/discover"])
@pytest.mark.parametrize("body", [
    MARK,                                              # a JSON string where an object belongs
    {MARK: "x"},                                       # an unexpected field NAME
    {"a": [MARK], "b": {"k": MARK}},                   # the marker as a value and as a nested key
    {"agent_id": "a", "name": MARK, "owner": 7},       # the marker next to a real wrong-typed field
])
def test_a_422_does_not_repeat_what_was_sent(client, path, body):
    r = client.post(path, json=body)
    assert r.status_code == 422, r.text
    assert MARK not in r.text, r.text
    assert all(set(e) == {"type", "loc", "msg"} for e in r.json()["detail"])
