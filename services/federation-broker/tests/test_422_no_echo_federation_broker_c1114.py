"""federation-broker's 422s never repeat the caller's text (C-1128; reviewer C-1123 F1, C-1109 F-C1109-2).

The service keeps its own handler, which dropped `input` but left `loc` alone: an object body whose key is the marker
came back as a `loc` part on POST /crossing. It now replaces such a name with the field-core `redacted_loc`. It does not
install the field-core handler, which would also replace the rule messages its validators write ("an outbound crossing
requires manifest") with fixed text: that is C-1123 F3, Don's to decide. Every value here is a made-up marker."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from federation_broker.api import create_app
from federation_broker.engine import BrokerEngine, ContractStore

MARK = "MADE-UP-MARKER-0123456789"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("FIELD_ORG_NAME", "Home Org")
    monkeypatch.delenv("FIELD_SHARED_SECRET", raising=False)
    return TestClient(create_app(engine=BrokerEngine(store=ContractStore(tmp_path / "contracts.sqlite3"))),
                      raise_server_exceptions=False)


@pytest.mark.parametrize("path, method", [("/crossing", "post"), ("/contracts/FED-1", "put")])
@pytest.mark.parametrize("body", [
    MARK,                                              # a JSON string where an object belongs
    {MARK: "x"},                                       # an unexpected field NAME
    {"a": [MARK], "b": {"k": MARK}},                   # the marker as a value and as a nested key
])
def test_a_422_does_not_repeat_what_was_sent(client, path, method, body):
    r = getattr(client, method)(path, json=body)
    assert r.status_code == 422, r.text
    assert MARK not in r.text, r.text
    assert all("input" not in e and e["msg"] for e in r.json()["detail"])   # the service keeps its own message text
